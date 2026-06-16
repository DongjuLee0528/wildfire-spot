# Wildfire Detection Quadruped Robot

Personal project integrating wildfire detection system into SpotMicroAI-based quadruped robot.

## Overview

Detection pipeline: Sensor primary detection → Camera secondary verification → GPS location logging → Obstacle avoidance → SLAM + A* autonomous patrol

## Hardware

- Platform: NVIDIA Jetson Nano B01
- Servos: JX CLS6336HV x12, MG995 x2
- Detection Sensors: MQ-2, SHT31, KY-026 x4, HC-SR04
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

- **FASDD** (Flame and Smoke Detection Dataset)
  - 100,000+ flame and smoke images, YOLO format
  - https://doi.org/10.57760/sciencedb.j00104.00103

- **Pyro-SDIS** by PyroNear
  - 33,636 wildfire smoke images, YOLO format
  - https://huggingface.co/datasets/pyronear/pyro-sdis

- **AI Hub Wildfire Detection Dataset**
  - Korean forest wildfire dataset
  - https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=71330

## Model

- Architecture: YOLOv10s
- Classes: fire, smoke
- Training: 200 epochs, imgsz=1280, batch=64
- Training Platform: Vast.ai (A100 80GB)
- Datasets: FASDD + Pyro-SDIS + AI Hub (301,060 images total)

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