import subprocess
import sys
import os

def install_package(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

try:
    import ultralytics
except ImportError:
    install_package("ultralytics")
    import ultralytics

try:
    import wandb
except ImportError:
    install_package("wandb")
    import wandb

if 'WANDB_API_KEY' in os.environ:
    wandb.login(key=os.environ['WANDB_API_KEY'])

from ultralytics import YOLO

def main():
    wandb.init(project="wildfire-detection", entity="dozoo0528-")

    print("Starting wildfire detection training with YOLOv10s...")

    model = YOLO('yolov10s.pt')

    results = model.train(
        data='/workspace/wildfire-dataset/data.yaml',
        epochs=150,
        batch=64,
        imgsz=1280,
        save_period=10,
        patience=30,
        device='cuda',
        project='/workspace/runs',
        name='wildfire_v1',
        workers=16,
        augment=True,
        hsv_h=0.015,
        hsv_s=0.7,
        flipud=0.5,
        fliplr=0.5
    )

    print("Training completed successfully!")
    print(f"Results saved to: {results.save_dir}")

if __name__ == "__main__":
    main()