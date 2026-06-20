import argparse
import logging
import os
from pathlib import Path

from utils.config import (
    DATASET_OUTPUT_PATH,
    TRAIN_AUGMENT,
    TRAIN_BATCH_SIZE,
    TRAIN_DATA_YAML,
    TRAIN_DEVICE,
    TRAIN_EPOCHS,
    TRAIN_EXIST_OK,
    TRAIN_FLIPLR,
    TRAIN_FLIPUD,
    TRAIN_HSV_H,
    TRAIN_HSV_S,
    TRAIN_HSV_V,
    TRAIN_IMAGE_SIZE,
    TRAIN_MODEL_PATH,
    TRAIN_MOSAIC,
    TRAIN_OUTPUT_DIR,
    TRAIN_PATIENCE,
    TRAIN_RESUME,
    TRAIN_RUN_NAME,
    TRAIN_SAVE_PERIOD,
    TRAIN_WORKERS,
    WANDB_ENTITY,
    WANDB_PROJECT,
)


LOGGER = logging.getLogger("wildfire.train")


def _setup_logging():
    output_dir = Path(TRAIN_OUTPUT_DIR).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / f"{TRAIN_RUN_NAME}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )
    LOGGER.info("Training log: %s", log_path)


def _require_path(path, description):
    path = Path(path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"{description} not found: {path}")
    return path


def _resolve_resume():
    if not TRAIN_RESUME:
        return False

    normalized = TRAIN_RESUME.lower()
    if normalized in {"1", "true", "yes", "auto"}:
        candidate = Path(TRAIN_OUTPUT_DIR) / TRAIN_RUN_NAME / "weights" / "last.pt"
        if not candidate.exists():
            raise FileNotFoundError(
                "Resume requested, but last checkpoint was not found: "
                f"{candidate}"
            )
        return str(candidate)

    return str(_require_path(TRAIN_RESUME, "Resume checkpoint"))


def _init_wandb():
    if os.environ.get("WANDB_MODE") == "disabled":
        LOGGER.info("Weights & Biases disabled by WANDB_MODE=disabled")
        return

    try:
        import wandb
    except ImportError:
        LOGGER.info("wandb is not installed; continuing without W&B logging")
        return

    api_key = os.environ.get("WANDB_API_KEY")
    if api_key:
        wandb.login(key=api_key)

    try:
        wandb.init(project=WANDB_PROJECT, entity=WANDB_ENTITY)
    except Exception as exc:
        LOGGER.warning("Failed to initialize wandb; continuing without it: %s", exc)


def _load_model(resume):
    from ultralytics import YOLO

    if resume:
        LOGGER.info("Resuming from checkpoint: %s", resume)
        return YOLO(resume)

    model_path = Path(TRAIN_MODEL_PATH).expanduser()
    if model_path.is_absolute() or os.sep in TRAIN_MODEL_PATH:
        _require_path(model_path, "Model file")
        LOGGER.info("Loading model from: %s", model_path)
        return YOLO(str(model_path))

    LOGGER.info("Loading model alias or cached weight: %s", TRAIN_MODEL_PATH)
    return YOLO(TRAIN_MODEL_PATH)


def _verify_training_inputs():
    dataset_dir = _require_path(DATASET_OUTPUT_PATH, "Unified dataset")
    data_yaml = _require_path(TRAIN_DATA_YAML, "Training data.yaml")

    for split in ("train", "val", "test"):
        _require_path(dataset_dir / f"{split}.txt", f"{split}.txt")

    LOGGER.info("Dataset root: %s", dataset_dir)
    LOGGER.info("Data yaml: %s", data_yaml)
    return data_yaml


def _verify_training_outputs(save_dir):
    save_dir = Path(save_dir)
    weights_dir = save_dir / "weights"
    best = weights_dir / "best.pt"
    last = weights_dir / "last.pt"
    results_csv = save_dir / "results.csv"

    missing = [str(path) for path in (best, last, results_csv) if not path.exists()]
    if missing:
        raise RuntimeError("Training finished, but expected outputs are missing: " + ", ".join(missing))

    LOGGER.info("Best checkpoint: %s", best)
    LOGGER.info("Last checkpoint: %s", last)
    LOGGER.info("Results CSV: %s", results_csv)

    events = list(save_dir.glob("events.out.tfevents.*"))
    if events:
        LOGGER.info("TensorBoard event files: %d", len(events))
    else:
        LOGGER.warning("No TensorBoard event file found in %s", save_dir)


def _print_config():
    print(f"DATASET_OUTPUT_PATH={DATASET_OUTPUT_PATH}")
    print(f"TRAIN_DATA_YAML={TRAIN_DATA_YAML}")
    print(f"TRAIN_PROJECT_PATH={TRAIN_OUTPUT_DIR}")
    print(f"TRAIN_NAME={TRAIN_RUN_NAME}")
    print(f"TRAIN_MODEL={TRAIN_MODEL_PATH}")
    print(f"TRAIN_EPOCHS={TRAIN_EPOCHS}")
    print(f"TRAIN_IMAGE_SIZE={TRAIN_IMAGE_SIZE}")
    print(f"TRAIN_BATCH_SIZE={TRAIN_BATCH_SIZE}")
    print(f"TRAIN_RESUME={TRAIN_RESUME or '<disabled>'}")


def _parse_args():
    parser = argparse.ArgumentParser(description="Train YOLOv10s wildfire baseline.")
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Print resolved training paths and settings without starting training.",
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    if args.print_config:
        _print_config()
        return

    _setup_logging()
    data_yaml = _verify_training_inputs()
    resume = _resolve_resume()
    _init_wandb()

    LOGGER.info("Starting wildfire detection training")
    LOGGER.info(
        "Config: model=%s epochs=%s imgsz=%s batch=%s device=%s project=%s name=%s resume=%s",
        TRAIN_MODEL_PATH,
        TRAIN_EPOCHS,
        TRAIN_IMAGE_SIZE,
        TRAIN_BATCH_SIZE,
        TRAIN_DEVICE,
        TRAIN_OUTPUT_DIR,
        TRAIN_RUN_NAME,
        resume,
    )

    model = _load_model(resume)
    results = model.train(
        data=str(data_yaml),
        epochs=TRAIN_EPOCHS,
        batch=TRAIN_BATCH_SIZE,
        imgsz=TRAIN_IMAGE_SIZE,
        save=True,
        save_period=TRAIN_SAVE_PERIOD,
        patience=TRAIN_PATIENCE,
        device=TRAIN_DEVICE,
        project=TRAIN_OUTPUT_DIR,
        name=TRAIN_RUN_NAME,
        exist_ok=TRAIN_EXIST_OK,
        workers=TRAIN_WORKERS,
        augment=TRAIN_AUGMENT,
        mosaic=TRAIN_MOSAIC,
        hsv_h=TRAIN_HSV_H,
        hsv_s=TRAIN_HSV_S,
        hsv_v=TRAIN_HSV_V,
        flipud=TRAIN_FLIPUD,
        fliplr=TRAIN_FLIPLR,
        plots=True,
        resume=bool(resume),
    )

    _verify_training_outputs(results.save_dir)
    LOGGER.info("Training completed successfully. Results saved to: %s", results.save_dir)


if __name__ == "__main__":
    main()
