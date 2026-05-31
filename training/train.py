"""
YOLOv10n Wildfire Detection Training Script

This script trains a YOLOv10n model for wildfire detection using fire and smoke datasets.
The model learns to detect fire (class 0) and smoke (class 1) objects in images.
Uses Apple Metal Performance Shaders (MPS) for GPU acceleration on macOS.
"""

from ultralytics import YOLO

def main():
    """
    Main function to train YOLOv10n model for wildfire detection.

    Loads a pre-trained YOLOv10n model and fine-tunes it on the wildfire dataset.
    Training configuration is optimized for fire and smoke detection with
    100 epochs, early stopping, and periodic model saving.
    """
    print("Starting wildfire detection training with YOLOv10n...")

    # Load pre-trained YOLOv10n model (nano version for faster training/inference)
    model = YOLO('yolov10n.pt')

    # Train the model with wildfire detection dataset
    results = model.train(
        data='/Users/dongjulee/Documents/AIdatasets/wildfire-dataset/data.yaml',  # Dataset config file
        epochs=100,           # Maximum number of training epochs
        batch=32,             # Batch size for training
        imgsz=640,            # Input image size (640x640 pixels)
        save_period=10,       # Save model checkpoint every 10 epochs
        patience=20,          # Early stopping patience (stop if no improvement for 20 epochs)
        device='mps',         # Use Apple Metal Performance Shaders for GPU acceleration
        project='/Users/dongjulee/Desktop/wildfire_spot/training/runs',  # Output directory
        name='wildfire_v1',   # Experiment name for this training run
        workers=12            # Number of CPU workers for data loading
    )

    # Training completion summary
    print("Training completed successfully!")
    print(f"Results saved to: {results.save_dir}")

# Execute training when script is run directly
if __name__ == "__main__":
    main()