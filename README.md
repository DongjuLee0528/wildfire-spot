## Content

1. Project Title & Introduction
- Title: Wildfire Detection Quadruped Robot
- Personal project integrating wildfire detection system into SpotMicroAI-based quadruped robot

2. Project Overview
- Detection pipeline: Sensor primary detection → Camera secondary verification → GPS location logging → Obstacle avoidance → SLAM + A* autonomous patrol

3. Hardware
- Platform: NVIDIA Jetson Nano B01
- Servos: JX CLS6336HV x12, MG995 x2
- Detection Sensors: MQ-2, SHT31, KY-026 x4, HC-SR04
- GPS: NEO-6M
- Camera: Logitech C922
- LiDAR: UNITREE L2

4. Software Structure
- Display folder structure as tree

5. Datasets
- FASDD (Flame and Smoke Detection Dataset)
  - 100,000+ flame and smoke images
  - YOLO format supported
  - https://doi.org/10.57760/sciencedb.j00104.00103

- Pyro-SDIS by PyroNear
  - 33,636 wildfire smoke images
  - YOLO format supported
  - https://huggingface.co/datasets/pyronear/pyro-sdis

- AI Hub Wildfire Detection Dataset
  - Korean forest wildfire dataset
  - Collected from actual fire simulations in Korean terrain
  - https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=71330

## Based On
- Based on [SpotMicroJetson](https://github.com/Road-Balance/SpotMicroJetson) by Road-Balance (GPL-3.0)
- Originally forked from [FlorianWilk's SpotMicroAI](https://github.com/FlorianWilk/SpotMicroAI)

## Copyright
Copyright (C) 2026 Dongjoo Lee

This is a modified version of the original work.
Major modifications include wildfire detection modules,
sensor integration, and YOLOv10n-based vision system.

## License
This project is licensed under the GNU General Public License v3.0.
See the [LICENSE](LICENSE) file for details.

## Rules
- Write in English
- Clean and concise
- No unnecessary content
- No comments