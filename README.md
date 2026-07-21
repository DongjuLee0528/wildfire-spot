# Wildfire Detection Quadruped Robot

Personal project integrating wildfire detection system into SpotMicroAI-based quadruped robot.

## Overview

Detection pipeline: Sensor primary detection → Camera secondary verification → GPS location logging → Obstacle avoidance → SLAM + A* autonomous patrol

## Hardware

- Platform: NVIDIA Jetson Nano B01
- Servos: JX CLS6336HV x12, MG995 x2
- Detection Sensors: DHT11, KY-026 x4, HC-SR04
- GPS: NEO-6M
- Camera: Logitech C922
- LiDAR: UNITREE L2

## Software Structure

```
wildfire_spot/
├── main.py
├── kinematicMotion.py
├── requirements.txt
├── Common/
│   └── multiprocess_kb.py
├── Kinematics/
│   ├── kinematics.py
│   └── README.md
├── detection/
├── hardware/
│   ├── gps_manager.py
│   ├── lidar_manager.py
│   ├── pan_tilt_controller.py
│   ├── sensor_manager.py
│   ├── servo_controller.py
│   ├── test_servos_cali.py
│   └── test_servos_offset.py
├── navigation/
├── training/
│   ├── preprocess.py
│   └── train.py
├── utils/
│   └── config.py
└── vision/
```

## Datasets

### Currently Integrated

| Dataset | Purpose | Format | Status |
| --- | --- | --- | --- |
| [FASDD](https://doi.org/10.57760/sciencedb.j00104.00103) | Flame and smoke detection (100,000+ images) | YOLO | Integrated |
| [Pyro-SDIS](https://huggingface.co/datasets/pyronear/pyro-sdis) | Wildfire smoke detection (33,636 images) | YOLO | Integrated |
| [AI Hub Wildfire Detection Dataset](https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=71330) | Korean forest wildfire detection | YOLO | Integrated |

### Pending Integration

| Dataset | Purpose | Format | Status |
| --- | --- | --- | --- |
| D-Fire | Fire and smoke detection | YOLO | Downloaded — Validation in Progress |
| NASA AMS Wildfire Dataset | Satellite wildfire detection | YOLO | Downloaded — Validation in Progress |
| FLAME3 | Fire detection benchmark | YOLO | Access Requested |

## Dataset Verification

Every dataset undergoes a rigorous verification pipeline before integration into training:

- Dataset integrity check
- Annotation validation
- Label quality inspection
- Bounding box validation
- Duplicate detection
- Image quality inspection
- Dataset statistics generation

## Model

- Architecture: YOLOv10s
- Classes: fire, smoke
- Training: 200 epochs, imgsz=1280, batch=32
- Training Platform: Vast.ai (A100 80GB)
- Datasets: Verified datasets are continuously integrated into the training dataset as they pass the verification pipeline.

## GPU Training Runbook

The training code is configured for a GPU server without local path edits. Defaults use `/workspace` paths and can be overridden with environment variables.

### Default Paths

| Setting | Default | Environment Override |
| --- | --- | --- |
| Dataset root | `/workspace/wildfire-dataset` | `WILDFIRE_DATASET_ROOT` |
| Unified dataset | `/workspace/wildfire-dataset/unified_dataset` | `WILDFIRE_DATASET_OUTPUT` |
| Training YAML | `/workspace/wildfire-dataset/unified_dataset/data.yaml` | `WILDFIRE_TRAIN_DATA_YAML` |
| Runs output | `/workspace/runs` | `WILDFIRE_TRAIN_PROJECT_PATH` |
| Model | `yolov10s.pt` | `WILDFIRE_TRAIN_MODEL` |
| Run name | `wildfire_v1` | `WILDFIRE_TRAIN_RUN_NAME` |
| D-Fire clean YOLO | `/workspace/wildfire-extra-datasets/DFire/clean_yolo` | `DFIRE_CLEAN_YOLO_PATH` |
| NASA AMS clean YOLO | `/workspace/wildfire-extra-datasets/NASA AMS/clean_yolo_patches` | `NASA_AMS_CLEAN_YOLO_PATH` |

### Server Setup

```bash
git pull origin main
python3 -m training.preprocess
python3 -m training.train
```

GPU server policy: do not edit code on the server. Pull `main`, preprocess, then train.

Before training, verify that these files exist:

```bash
ls /workspace/wildfire-dataset/unified_dataset/data.yaml
ls /workspace/wildfire-dataset/unified_dataset/train.txt
ls /workspace/wildfire-dataset/unified_dataset/val.txt
ls /workspace/wildfire-dataset/unified_dataset/test.txt
```

### Resume Training

Resume from the default `last.pt` checkpoint:

```bash
WILDFIRE_TRAIN_RESUME=true python3 -m training.train
```

Resume from an explicit checkpoint:

```bash
WILDFIRE_TRAIN_RESUME=/workspace/runs/wildfire_v1/weights/last.pt python3 -m training.train
```

Expected outputs:

- `/workspace/runs/wildfire_v1/weights/best.pt`
- `/workspace/runs/wildfire_v1/weights/last.pt`
- `/workspace/runs/wildfire_v1/results.csv`
- `/workspace/runs/wildfire_v1.log`
- TensorBoard event files under `/workspace/runs/wildfire_v1/`
- Ultralytics result plots, metrics CSV, and confusion matrix under `/workspace/runs/wildfire_v1/`

TensorBoard:

```bash
tensorboard --logdir /workspace/runs
```

Baseline settings are YOLOv10s, 200 epochs, image size 1280, batch size 32, and Unified Dataset v1.0 with 173,600 images. Run the baseline first. Do not tune augmentation, optimizer, model size, confidence thresholds, or other performance settings before the baseline finishes. `results.csv` is updated during training, so the 50 epoch point can be checked from the run directory without changing code. If an OOM occurs, rerun with a smaller batch, for example `WILDFIRE_TRAIN_BATCH_SIZE=16 python3 -m training.train`. Record mAP50, mAP50-95, precision, recall, F1, confusion matrix, and total training time before changing optimization settings.

## Research

- **Daelim University** — Undergraduate Research Project
- **Korea Institute of Information & Telecommunication Facilities Engineering**
- **2026 Summer Conference**

## Roadmap

**Completed**

- [x] Dataset preprocessing pipeline
- [x] Dataset verification tools
- [x] Fire detection logic
- [x] GPS manager
- [x] LiDAR manager
- [x] Sensor manager
- [x] YOLO training pipeline

**In Progress**

- [ ] D-Fire integration
- [ ] NASA AMS integration
- [ ] FLAME3 integration
- [ ] Camera verification

**Planned**

- [ ] TensorRT optimization
- [ ] Real robot deployment
- [ ] Field testing
- [ ] Conference paper publication

## Hardware References

- Original 3D Model: [SpotMicro](https://www.thingiverse.com/thing:3445283) by KDY0523 (CC BY 4.0)
- Modified by [Road-Balance](https://github.com/Road-Balance/SpotMicroJetson) (CC BY 4.0)
- Further modified by Dongju Lee (CC BY 4.0)

## Based On

- Based on [SpotMicroJetson](https://github.com/Road-Balance/SpotMicroJetson) by Road-Balance (GPL-3.0)
- Originally forked from [FlorianWilk's SpotMicroAI](https://github.com/FlorianWilk/SpotMicroAI)

## Copyright

Copyright (C) 2026 Dongjoo Lee

This is a modified version of the original work.
Major modifications include wildfire detection modules,
sensor integration, and YOLOv10s-based vision system.

## License

- Hardware (STL files): CC BY 4.0
- Software: GNU General Public License v3.0

See the [LICENSE](LICENSE) file for details.
