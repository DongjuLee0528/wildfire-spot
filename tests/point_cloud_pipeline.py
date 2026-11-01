import json
import logging
import os
from pathlib import Path
import queue
import selectors
import shutil
import signal
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hardware.point_cloud_manager import PointCloudManager
from robot.point_cloud_uploader import PointCloudUploader
import requests


class CleanupFailed(RuntimeError):
    pass


def main():
    stopped = threading.Event()
    signaled = False
    commands = queue.Queue(maxsize=8)
    reader_error = []
    manager = uploader = None
    known = set()
    cleaned = False
    cleanup_failure = None

    def stopping():
        return stopped.is_set() or signaled

    def on_signal(_signal, _frame):
        nonlocal signaled
        signaled = True

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    def read_commands():
        pending = bytearray()
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(0, selectors.EVENT_READ)
                while not stopping():
                    if not selector.select(0.1):
                        continue
                    chunk = os.read(0, 4096)
                    if not chunk:
                        stopped.set()
                        return
                    pending.extend(chunk)
                    if len(pending) > 8192:
                        raise ValueError('Command exceeds limit')
                    while b'\n' in pending:
                        line, _, rest = pending.partition(b'\n')
                        pending[:] = rest
                        commands.put_nowait(json.loads(line))
        except Exception as error:
            reader_error.append(type(error).__name__)
            stopped.set()

    reader = threading.Thread(target=read_commands, name='pipeline-commands', daemon=True)
    reader.start()

    def reply(event, **data):
        print(json.dumps({'event': event, **data}), flush=True)

    def command():
        while not stopping():
            try:
                return commands.get(timeout=0.1)
            except queue.Empty:
                continue
        return None

    def status():
        current = manager.get_status()
        if current['pid'] is not None:
            known.add(current['pid'])
        return {'state': current['state'], 'pid': current['pid'], 'restarts': current['restart_count'],
                'uploadState': uploader.get_status()['state'], 'pids': sorted(known)}

    def wait_for(predicate, timeout=5):
        end = time.monotonic() + timeout
        while time.monotonic() < end and not stopping():
            if predicate():
                return
            time.sleep(0.01)
        if stopping():
            raise InterruptedError('Fixture shutdown requested')
        raise TimeoutError('Source condition not reached')

    def reaped(pid):
        try:
            result, _ = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return True
        return result == pid

    def cleanup():
        nonlocal cleaned, cleanup_failure
        if cleaned:
            if cleanup_failure is not None:
                raise cleanup_failure
            return
        cleaned = True
        errors = []
        if manager:
            current = manager.get_status()['pid']
            if current is not None:
                known.add(current)
        if uploader:
            uploader.request_stop()
        try:
            if manager:
                manager.close()
        except Exception as error:
            errors.append('ManagerClose:' + type(error).__name__)
        finally:
            try:
                if uploader:
                    uploader.close()
            except Exception as error:
                errors.append('UploaderClose:' + type(error).__name__)
        for pid in known:
            if not reaped(pid):
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    logging.getLogger(__name__).debug('Fixture receiver already exited')
                end = time.monotonic() + 1
                while time.monotonic() < end and not reaped(pid):
                    time.sleep(0.01)
                if not reaped(pid):
                    errors.append('ReceiverNotReaped')
        stopped.set()
        reader.join(timeout=1)
        if reader.is_alive():
            errors.append('CommandReaderNotStopped')
        if errors:
            cleanup_failure = CleanupFailed('Source cleanup failed: ' + ','.join(errors))
            raise cleanup_failure

    try:
        config = command()
        if config is None:
            if reader_error:
                raise ValueError('Command reader failed: ' + ','.join(reader_error))
            return 0
        address = urlsplit(config['baseUrl'])
        if address.scheme != 'http' or address.hostname != '127.0.0.1' or not address.port or address.path or address.query or address.fragment or address.username:
            raise ValueError('Only a loopback fixture server is allowed')
        directory = Path(config['directory']).resolve(strict=True)
        sdk = Path(os.environ['UNITREE_LIDAR_SDK_ROOT']).resolve(strict=True)
        if not (sdk / 'include/unitree_lidar_sdk.h').is_file():
            raise ValueError('SDK headers missing')
        binary = directory / 'fake-l2-receiver'
        compiler = os.environ.get('CXX') or shutil.which('c++')
        if not compiler:
            raise ValueError('C++ compiler missing')
        args = [compiler, '-std=c++17', '-Wall', '-Wextra', '-Wpedantic', '-pthread',
                '-isystem', str(sdk / 'include'), str(ROOT / 'hardware/l2_receiver/main.cpp'),
                str(ROOT / 'hardware/l2_receiver/tests/fake_sdk.cpp'), '-o', str(binary)]
        with (directory / 'compile.log').open('wb') as diagnostic:
            process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=diagnostic, start_new_session=True)
            end = time.monotonic() + 20
            try:
                while process.poll() is None:
                    if stopping():
                        raise InterruptedError('Fixture compilation shutdown requested')
                    if time.monotonic() > end:
                        raise TimeoutError('Fixture compilation timed out')
                    time.sleep(0.02)
                if process.returncode:
                    with (directory / 'compile.log').open('rb') as failed:
                        failed.seek(0, os.SEEK_END)
                        failed.seek(max(0, failed.tell() - 2048))
                        tail = failed.read(2048).decode('utf-8', errors='replace')
                    raise RuntimeError('Fixture compilation failed: ' + tail)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=2)
        if stopping():
            return 0
        control = directory / 'scenario'

        def scenario(value):
            temporary = directory / 'scenario.next'
            temporary.write_text(value, encoding='ascii')
            temporary.replace(control)

        scenario('normal')
        os.environ['L2_TEST_CONTROL_FILE'] = str(control)
        manager = PointCloudManager(binary, local_ip='127.0.0.1', lidar_ip='127.0.0.2')

        def session_factory():
            session = requests.Session()
            session.trust_env = False
            return session

        uploader = PointCloudUploader(manager, config['serial'], config['key'], config['baseUrl'], session_factory=session_factory)
        manager.start()
        uploader.start()
        wait_for(lambda: status()['state'] == 'STREAMING' and uploader.get_status()['state'] == 'STREAMING')
        reply('ready', **status())
        while not stopping():
            request = command()
            if request is None:
                break
            action = request['command']
            if action == 'stop':
                break
            if action == 'crash':
                old = manager.get_status()['pid']
                known.add(old)
                scenario('run_std')
                wait_for(lambda: manager.get_status()['state'] == 'RESTARTING')
                if not reaped(old):
                    raise RuntimeError('Exited receiver was not reaped')
                scenario('recovered')
                wait_for(lambda: status()['state'] == 'STREAMING' and status()['pid'] != old and status()['restarts'] == 1)
            elif action == 'stale':
                wait_for(lambda: status()['state'] == 'STALE', timeout=3)
            elif action in ('normal', 'empty', 'max', 'idle'):
                scenario(action)
            elif action != 'status':
                raise ValueError('Unknown source command')
            reply(action, **status())
        if reader_error:
            raise ValueError('Command reader failed: ' + ','.join(reader_error))
        before = status()
        cleanup()
        reply('stopped', before=before, **status())
        return 0
    except CleanupFailed:
        raise
    except Exception as error:
        if isinstance(error, InterruptedError) and stopping() and not reader_error:
            return 0
        reply('error', kind=type(error).__name__, message=str(error))
        return 1
    finally:
        cleanup()


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    try:
        exit_code = main()
    except CleanupFailed as error:
        print(json.dumps({'event': 'error', 'kind': type(error).__name__, 'message': str(error)}), flush=True)
        exit_code = 1
    raise SystemExit(exit_code)
