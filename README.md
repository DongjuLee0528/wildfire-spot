# Wildfire Detection Quadruped Robot

An AIoT-based autonomous quadruped robot that integrates wildfire detection, multi-sensor verification, robot control, and real-time web monitoring.

This project was independently designed and technically implemented by **Dongju Lee** as an undergraduate research project at Daelim University College. The system was presented as a first-author oral presentation at the 2026 Summer Conference of the Korea Institute of Information and Telecommunication Facilities Engineering and received an Outstanding Paper Award.

## Project Overview

The system combines a YOLOv10s fire-and-smoke detector with four KY-026 flame sensors to reduce reliance on a single detection source.

A Jetson Orin Nano Super performs AI inference, sensor processing, robot control, and communication with the monitoring system. Detection results, sensor readings, GPS data, robot status, and evidence images are delivered to a Spring Boot server and displayed through a React dashboard.

The project also integrates inverse-kinematics-based quadruped locomotion, LiDAR mapping, GPS positioning, camera control, and A*-based path-planning components.

## Key Features

* YOLOv10s fire and smoke detection
* Six-dataset integration and preprocessing pipeline
* Jetson Orin Nano Super edge inference
* Four-direction KY-026 flame-sensor verification
* Inverse-kinematics-based quadruped locomotion
* LiDAR mapping and A*-based path-planning components
* GPS position collection
* Pan-tilt camera control
* Automatic and manual control modes
* Spring Boot REST API server
* React monitoring dashboard
* JWT-based user and device authentication
* Real-time camera and detection monitoring
* Fire-event and evidence-image capture
* Sensor, GPS, heartbeat, and robot-status reporting

## System Architecture

```text
Logitech C922 Camera
        |
        v
YOLOv10s Fire/Smoke Detection
        |
        +--------------------------+
        |                          |
        v                          v
Visual Detection Result     KY-026 Flame Sensors x4
        |                          |
        +------------+-------------+
                     |
                     v
             Fire Decision Logic
                     |
                     v
          Jetson Orin Nano Super
                     |
        +------------+-------------+
        |                          |
        v                          v
 Robot Control Runtime       FastAPI Robot API
        |                          |
        v                          v
Inverse Kinematics      Spring Boot REST Server
Sensor / GPS / LiDAR                |
                                     v
                             React Dashboard
```

The camera-based detector and flame sensors form a dual-verification structure. A visual detection can generate a suspected-fire state, while simultaneous visual and flame-sensor detections provide cross-validated fire evidence.

## Hardware

| Component                       | Model or Specification        | Purpose                                            |
| ------------------------------- | ----------------------------- | -------------------------------------------------- |
| Edge computer                   | NVIDIA Jetson Orin Nano Super | AI inference, sensor processing, and robot control |
| Quadruped platform              | Modified SpotMicro platform   | Mobile wildfire-monitoring platform                |
| Main servos                     | JX CLS6336HV x12              | Leg-joint actuation                                |
| Camera servos                   | MG995 x2                      | Pan-tilt camera control                            |
| Servo drivers                   | PCA9685                       | Multi-channel servo control                        |
| Camera                          | Logitech C922                 | Fire and smoke image acquisition                   |
| LiDAR                           | Unitree L2                    | Environmental mapping and navigation input         |
| Flame sensors                   | KY-026 x4                     | Four-direction flame detection                     |
| Temperature and humidity sensor | DHT11                         | Environmental sensing                              |
| GPS                             | NEO-6M                        | Robot location acquisition                         |
| Distance sensor                 | HC-SR04                       | Short-range obstacle sensing                       |

## Hardware Design and Attribution

The robot is based on the open-source SpotMicro platform originally published by KDY0523.

Leg-related STL assets from the SpotMicroJetson project by Road-Balance were used as a foundation. The body, sensor mounts, and other structural components were redesigned or newly created in Fusion 360 to support the wildfire-detection hardware.

The project does not claim ownership of the original SpotMicro or SpotMicroJetson designs. Original and modified assets are identified in the [Hardware References](#hardware-references) and [License](#license) sections.

## Software Structure

```text
wildfire-spot/
├── main.py
├── kinematicMotion.py
├── requirements.txt
├── Common/
│   └── multiprocess_kb.py
├── Kinematics/
│   ├── kinematics.py
│   └── README.md
├── detection/
│   ├── fire_detection.py
│   └── fire_events.py
├── hardware/
│   ├── camera_control_manager.py
│   ├── gps_manager.py
│   ├── lidar_manager.py
│   ├── pan_tilt_controller.py
│   ├── sensor_manager.py
│   └── servo_controller.py
├── navigation/
│   └── patrol_zone_manager.py
├── robot/
│   ├── manual_control_manager.py
│   ├── mode_control_manager.py
│   ├── robot_api_server.py
│   ├── robot_data_collector.py
│   └── spring_api_client.py
├── training/
│   ├── preprocess.py
│   └── train.py
├── vision/
│   └── camera_vision.py
├── utils/
│   ├── config.py
│   ├── gait_diagnostics.py
│   ├── logger.py
│   └── state_machine.py
├── server/
│   └── Spring Boot service
├── web/
│   └── React monitoring dashboard
├── models/
│   └── wildfire_baseline/
├── tests/
└── docs/
```

## Dataset Integration

The final preprocessing pipeline supports six wildfire-related datasets.

| Dataset                 | Primary Source Type                     | Original Format | Unified Format | Status     |
| ----------------------- | --------------------------------------- | --------------- | -------------- | ---------- |
| FASDD                   | Ground-camera fire and smoke images     | YOLO            | YOLO           | Integrated |
| FASDD_UAV               | UAV fire and smoke images               | YOLO            | YOLO           | Integrated |
| PyroNear                | Wildfire smoke images                   | Parquet         | YOLO           | Integrated |
| AI Hub Wildfire Dataset | Korean wildfire imagery                 | JSON            | YOLO           | Integrated |
| D-Fire                  | Fire and smoke images                   | YOLO            | YOLO           | Integrated |
| NASA AMS                | Airborne multispectral wildfire imagery | TIFF/YOLO       | RGB JPEG/YOLO  | Integrated |

The unified class mapping is:

```text
0 = fire
1 = smoke
```

### Unified Dataset Build

The verified repository baseline uses the following split:

| Split      |  Images |
| ---------- | ------: |
| Train      | 138,880 |
| Validation |  17,360 |
| Test       |  17,360 |
| Total      | 173,600 |

The preprocessing pipeline uses a fixed split seed and deterministic path ordering to support reproducible dataset generation.

## Dataset Preprocessing and Verification

The preprocessing pipeline performs the following operations before publishing a unified dataset:

* Input dataset availability checks
* Image and label pair validation
* Class-ID normalization
* Bounding-box validation
* Invalid annotation filtering
* Empty-label handling
* NASA AMS TIFF-to-RGB JPEG conversion
* Train, validation, and test split generation
* Deterministic sorting and fixed-seed splitting
* Output-path verification
* Atomic publication of the verified dataset build
* Recovery of the previous output if dataset publication fails

A dataset build is not published when required source files are missing or verification fails.

## AI Model

| Item                    | Configuration                 |
| ----------------------- | ----------------------------- |
| Architecture            | YOLOv10s                      |
| Classes                 | `fire`, `smoke`               |
| Training epochs         | 200                           |
| Best checkpoint epoch   | 193                           |
| Input size              | 640                           |
| Batch size              | 16                            |
| Early-stopping patience | 30                            |
| Training GPU            | NVIDIA A100 80 GB             |
| Edge platform           | NVIDIA Jetson Orin Nano Super |

The training configuration uses augmentation techniques including mosaic augmentation, HSV transformation, horizontal flipping, and vertical flipping.

## Model Performance

The best checkpoint reported in the conference paper achieved:

| Metric       | Result |
| ------------ | -----: |
| Precision    | 84.97% |
| Recall       | 77.29% |
| mAP@0.5      | 85.06% |
| mAP@0.5:0.95 | 59.89% |

These results are validation-set metrics from the reported experimental configuration. They do not establish performance under every real-world wildfire, weather, terrain, or lighting condition.

The trained checkpoint was applied to the Jetson Orin Nano Super, where fire and smoke inference was integrated with the robot system.

## Fire Detection and Sensor Fusion

The runtime combines camera-based object detection with four flame sensors.

```text
Camera detection only
        |
        v
Suspected-fire state

Flame-sensor detection only
        |
        v
Sensor warning state

Camera detection + flame-sensor detection
        |
        v
Cross-validated fire state
```

When a visual event is detected, the system can:

* Display fire or smoke bounding boxes
* Record the event time
* Associate GPS and sensor information
* Capture an evidence image
* Upload event data to the Spring Boot server
* Display the event through the React dashboard

Actual open-flame wildfire testing was not performed for safety reasons. The vision pipeline was evaluated using wildfire imagery, and the hardware and software components were integrated on the physical robot.

## Robot Control

The robot-control system includes:

* Inverse-kinematics calculations
* Per-joint servo-angle generation
* Quadruped posture and gait commands
* Manual movement commands
* Automatic and manual operating modes
* Camera pan-tilt control
* Patrol-zone management
* Gait diagnostics
* Invalid-angle and control-failure handling

Continuous locomotion stability on uneven outdoor terrain remains an area for further improvement.

## Navigation

The navigation components include:

* Unitree L2 LiDAR data acquisition
* 3D environmental mapping
* GPS position acquisition
* A*-based path-planning experiments
* Patrol-zone representation
* Obstacle-awareness components

LiDAR mapping and path-planning components were implemented and evaluated as part of the prototype. Long-duration autonomous patrol and outdoor forest-field validation have not yet been completed.

## Monitoring System

The monitoring system connects the following components:

```text
Robot Core
    |
    v
FastAPI Robot API
    |
    v
Spring Boot REST Server
    |
    v
React Monitoring Dashboard
```

Implemented functions include:

* User authentication
* Device authentication
* JWT-based access control
* Device registration
* Device heartbeat monitoring
* Fire-event upload and retrieval
* Sensor-data upload and retrieval
* GPS-data upload and retrieval
* Robot mode control
* Manual movement commands
* Camera commands
* Mission and patrol-zone management
* Evidence capture
* Real-time camera monitoring

## GPU Training Runbook

The training code is configured for GPU-server execution without source-code path modifications. Default paths can be overridden through environment variables.

### Default Paths

| Setting          | Default                                                          | Environment Override          |
| ---------------- | ---------------------------------------------------------------- | ----------------------------- |
| Dataset root     | `/workspace/wildfire-dataset`                                    | `WILDFIRE_DATASET_ROOT`       |
| Unified dataset  | `/workspace/wildfire-dataset/unified_dataset`                    | `WILDFIRE_DATASET_OUTPUT`     |
| Training YAML    | `/workspace/wildfire-dataset/unified_dataset/data.yaml`          | `WILDFIRE_TRAIN_DATA_YAML`    |
| Runs output      | `/workspace/runs`                                                | `WILDFIRE_TRAIN_PROJECT_PATH` |
| Model            | `yolov10s.pt`                                                    | `WILDFIRE_TRAIN_MODEL`        |
| Run name         | `wildfire_v1`                                                    | `WILDFIRE_TRAIN_RUN_NAME`     |
| D-Fire dataset   | `/workspace/wildfire-extra-datasets/DFire/clean_yolo`            | `DFIRE_CLEAN_YOLO_PATH`       |
| NASA AMS dataset | `/workspace/wildfire-extra-datasets/NASA AMS/clean_yolo_patches` | `NASA_AMS_CLEAN_YOLO_PATH`    |

### Server Setup

```bash
git pull origin main
python3 -m training.preprocess
python3 -m training.train
```

Before training, verify that the unified dataset contains the required configuration and split files:

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

Resume from a specific checkpoint:

```bash
WILDFIRE_TRAIN_RESUME=/workspace/runs/wildfire_v1/weights/last.pt \
python3 -m training.train
```

### Expected Training Outputs

```text
/workspace/runs/wildfire_v1/weights/best.pt
/workspace/runs/wildfire_v1/weights/last.pt
/workspace/runs/wildfire_v1/results.csv
/workspace/runs/wildfire_v1.log
```

Ultralytics result plots, confusion matrices, and TensorBoard event files are also written to the run directory.

Start TensorBoard with:

```bash
tensorboard --logdir /workspace/runs
```

## Testing

The repository contains tests for robot-control and server-integration behaviour, including:

* Inverse-kinematics failure handling
* Gait diagnostics
* Spring Boot integration
* Robot gateway communication
* Dashboard API behaviour

Run the Python tests with:

```bash
python3 -m unittest discover -s tests
```

Run the Spring Boot tests with:

```bash
cd server
./gradlew test
```

## Research Publication

**Korean title**

> AIoT 기반 산불 감지 자율주행 사족보행 로봇 구현

**English title**

> Implementation of an AIoT-Based Autonomous Quadruped Robot for Wildfire Detection

**Authors**

* Dongju Lee — First author and oral presenter
* Mijeom Kim — Second author

**Affiliation**

* Department of Computer Information, Daelim University College

**Presentation**

* 2026 Summer Conference of the Korea Institute of Information and Telecommunication Facilities Engineering
* Oral presentation
* August 26–28, 2026

**Award**

* Outstanding Paper Award
* August 28, 2026

## Implementation Status

### Completed

* [x] Physical quadruped robot construction
* [x] Body and sensor-mount modification
* [x] Six-dataset preprocessing pipeline
* [x] Dataset verification pipeline
* [x] YOLOv10s training and evaluation
* [x] Jetson Orin Nano Super inference integration
* [x] Camera-based fire and smoke detection
* [x] Four-direction flame-sensor integration
* [x] GPS manager
* [x] LiDAR manager
* [x] Sensor manager
* [x] Servo controller
* [x] Inverse-kinematics-based robot control
* [x] LiDAR mapping experiment
* [x] A*-based path-planning experiment
* [x] FastAPI robot interface
* [x] Spring Boot REST server
* [x] React monitoring dashboard
* [x] Fire-event and evidence-image handling
* [x] Conference paper publication
* [x] Oral conference presentation
* [x] Outstanding Paper Award

### In Progress

* [ ] Continuous-walking stability improvements
* [ ] Hardware and control-algorithm refinement
* [ ] Additional runtime verification

### Planned

* [ ] Long-duration outdoor field testing
* [ ] Night, haze, and severe-weather dataset expansion
* [ ] TensorRT and FP16 inference optimization
* [ ] Uneven-terrain locomotion validation
* [ ] LiDAR-based obstacle-avoidance validation
* [ ] Long-duration autonomous forest patrol testing

## Known Limitations

* The system was not tested with a real uncontrolled wildfire.
* Vision-model metrics were measured on a validation dataset and do not guarantee field performance.
* Long-duration operation in an actual forest environment has not been validated.
* Continuous quadruped locomotion requires further stability improvements.
* LiDAR-based obstacle avoidance requires additional physical validation.
* TensorRT and FP16 optimization have not yet been completed.
* Weather, smoke density, camera exposure, and lighting conditions may affect detection performance.

## Hardware References

* [SpotMicro by KDY0523](https://www.thingiverse.com/thing:3445283) — original open-source hardware design, CC BY 4.0
* [SpotMicroJetson by Road-Balance](https://github.com/Road-Balance/SpotMicroJetson) — modified SpotMicro-based platform, CC BY 4.0
* Body, sensor mounts, and integration modifications by Dongju Lee

## Software References

* [SpotMicroJetson](https://github.com/Road-Balance/SpotMicroJetson) by Road-Balance
* [SpotMicroAI](https://github.com/FlorianWilk/SpotMicroAI) by Florian Wilk
* [YOLOv10](https://github.com/THU-MIG/yolov10)

## Dataset References

* [FASDD](https://doi.org/10.57760/sciencedb.j00104.00103)
* [PyroNear / Pyro-SDIS](https://huggingface.co/datasets/pyronear/pyro-sdis)
* [AI Hub Wildfire Detection Dataset](https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=71330)
* D-Fire
* NASA AMS Wildfire Dataset

Each dataset remains subject to its original provider's terms, license, and usage restrictions.

## Project Author

**Dongju Lee**

Independent system design and technical implementation:

* Project concept
* Hardware modification and integration
* Mechanical-part redesign
* Dataset preprocessing
* AI-model training and evaluation
* Jetson inference integration
* Sensor integration
* Robot-control software
* Backend architecture
* Monitoring dashboard
* Testing
* Research paper preparation
* Oral presentation

## Copyright

Copyright (C) 2026 Dongju Lee

This repository contains modifications and additions built on open-source SpotMicro-related work.

Major original contributions include:

* Wildfire-detection modules
* Six-dataset preprocessing pipeline
* YOLOv10s training and evaluation pipeline
* Multi-sensor fire-verification logic
* Jetson Orin Nano Super integration
* Robot-control integration
* Spring Boot and React monitoring system
* Modified body and sensor-mount designs

No ownership is claimed over upstream open-source assets or third-party datasets.

## License

* Hardware STL files derived from or based on the referenced SpotMicro projects: CC BY 4.0
* Software derived from the referenced GPL-licensed projects: GNU General Public License v3.0
* Third-party datasets, libraries, models, and assets remain subject to their original licenses and terms

See [LICENSE](LICENSE) for the complete license text.
