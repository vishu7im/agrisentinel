"""The class registry. Single source of truth for download.py, prepare.py and train.py.

PlantVillage ships 38 classes across 14 crops. We keep three crops (tomato, potato, corn)
and 14 classes, because the prototype scans one crop's field at a time and a model that
also knows about apple scab just adds confusable classes for no demo value.

The `tile_label` column is the load-bearing one. `contract/run_state.schema.json` requires
tiles[].label to be a snake_case slug like "late_blight" or "healthy" — that string is what
Dev B's heatmap colours and what the Spread Analyst looks up its severity weight by. Every
per-crop healthy class collapses to plain "healthy": the run already knows its crop, so
"tomato_healthy" would only be a second name for the same thing.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CropClass:
    """One PlantVillage folder and how it surfaces in the run state."""

    folder: str  # exact directory name in the PlantVillage repo — do not tidy it
    crop: str  # tomato | potato | corn
    tile_label: str  # what lands in tiles[].label

    @property
    def key(self) -> str:
        """Stable model-class name, e.g. 'tomato__late_blight'."""
        return f"{self.crop}__{self.tile_label}"


# 14 classes: 7 tomato, 3 potato, 4 corn — one healthy class per crop.
#
# Dropped on purpose, all tomato: Spider_mites (a pest, not a disease, so the treatment
# corpus in A6 has nothing to say about it), Target_Spot and Tomato_mosaic_virus (both
# visually collide with classes we keep, and every confusable pair we add costs macro-F1
# on the slide in A9). Late blight is kept across both tomato and potato because it is the
# demo disease and the same pathogen genuinely crosses those two crops.
CLASSES: tuple[CropClass, ...] = (
    # --- tomato ---
    CropClass("Tomato___Bacterial_spot", "tomato", "bacterial_spot"),
    CropClass("Tomato___Early_blight", "tomato", "early_blight"),
    CropClass("Tomato___Late_blight", "tomato", "late_blight"),
    CropClass("Tomato___Leaf_Mold", "tomato", "leaf_mold"),
    CropClass("Tomato___Septoria_leaf_spot", "tomato", "septoria_leaf_spot"),
    CropClass("Tomato___Tomato_Yellow_Leaf_Curl_Virus", "tomato", "yellow_leaf_curl_virus"),
    CropClass("Tomato___healthy", "tomato", "healthy"),
    # --- potato ---
    CropClass("Potato___Early_blight", "potato", "early_blight"),
    CropClass("Potato___Late_blight", "potato", "late_blight"),
    CropClass("Potato___healthy", "potato", "healthy"),
    # --- corn ---
    CropClass("Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot", "corn", "gray_leaf_spot"),
    CropClass("Corn_(maize)___Common_rust_", "corn", "common_rust"),
    CropClass("Corn_(maize)___Northern_Leaf_Blight", "corn", "northern_leaf_blight"),
    CropClass("Corn_(maize)___healthy", "corn", "healthy"),
)

# Model class order. Sorted so the index a checkpoint was trained with can never depend on
# the order someone happened to type the tuple above in.
CLASS_KEYS: tuple[str, ...] = tuple(sorted(c.key for c in CLASSES))

BY_KEY: dict[str, CropClass] = {c.key: c for c in CLASSES}
BY_FOLDER: dict[str, CropClass] = {c.folder: c for c in CLASSES}

CROPS: tuple[str, ...] = tuple(sorted({c.crop for c in CLASSES}))


def key_to_index(key: str) -> int:
    return CLASS_KEYS.index(key)
