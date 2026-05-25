from ultralytics import YOLO

def main():
    print("Starting wildfire detection training with YOLOv10n...")

    model = YOLO('yolov10n.pt')

    results = model.train(
        data='/Users/dongjulee/Documents/AIdatasets/wildfire-dataset/data.yaml',
        epochs=100,
        batch=16,
        imgsz=640,
        save_period=10,
        patience=20,
        device='mps',
        project='/Users/dongjulee/Desktop/wildfire_spot/training/runs',
        name='wildfire_v1',
        workers=4
    )

    print("Training completed successfully!")
    print(f"Results saved to: {results.save_dir}")

if __name__ == "__main__":
    main()