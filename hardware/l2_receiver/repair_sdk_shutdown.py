import argparse
import hashlib
import os
from pathlib import Path
import tempfile


REPAIRS = {
    'aarch64': ('4e334b67c1a92152c89363d8014a6e361d7bf590e58484d7d6ddc8541389de28',
                71070, '1a0100001f000000', '1a01000029000000'),
    'x86_64': ('a8530545cbd435e3a96b9a099cd57921202aed3d690066f55ea0ade4310212d3',
               77346, '040000001e000000', '0400000029000000'),
}


def repair_archive(data, architecture):
    if architecture not in REPAIRS:
        raise ValueError('Unsupported SDK architecture: ' + architecture)
    digest, offset, original, replacement = REPAIRS[architecture]
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('SDK archive does not match the pinned revision; refusing repair')
    original, replacement = bytes.fromhex(original), bytes.fromhex(replacement)
    if data[offset:offset + len(original)] != original:
        raise ValueError('SDK relocation does not match the verified destructor call')
    return data[:offset] + replacement + data[offset + len(original):]


def main():
    parser = argparse.ArgumentParser(description='Repair the pinned SDK UDP destructor relocation in a build copy')
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('architecture', choices=REPAIRS)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('Output must differ from the original SDK archive')
    try:
        repaired = repair_archive(args.source.read_bytes(), args.architecture)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=args.output.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(repaired)
            os.replace(temporary, args.output)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
    except (OSError, ValueError) as error:
        parser.exit(1, 'SDK shutdown repair failed: ' + str(error) + '\n')
    print('Repaired pinned SDK shutdown relocation: ' + args.architecture +
          ' sha256=' + hashlib.sha256(repaired).hexdigest())


if __name__ == '__main__':
    main()
