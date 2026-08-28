"""Restricted AnkiConnect extension for Anki Generator CLI maintenance."""

from __future__ import annotations

import importlib


OWNED_MODEL_NAME = "AG Production Recall v1"
OWNED_TEMPLATE_NAME = "AG Production Recall"
OWNED_MARKER = "anki-generator-existing-production-v1"
OWNED_FIELDS = {
    "Word",
    "AG_SourceNoteID",
    "AG_RunID",
    "ProductionFront",
    "ProductionBack",
    "WordAudio",
}
ALLOWED_SORT_FIELDS = {"Word", "AG_SourceNoteID"}


def _model_field_set_sort(self, modelName, fieldName):
    """Set the sort field only on the exact app-owned recall note type."""
    if modelName != OWNED_MODEL_NAME:
        raise Exception("This helper only manages the app-owned recall note type.")
    if fieldName not in ALLOWED_SORT_FIELDS:
        raise Exception("Unsupported recall sort field.")

    models = self.collection().models
    model = models.by_name(modelName)
    if model is None:
        raise Exception("The app-owned recall note type does not exist.")

    fields = model.get("flds") or []
    field_names = [field.get("name") for field in fields]
    templates = model.get("tmpls") or []
    owned_template = next(
        (
            template
            for template in templates
            if template.get("name") == OWNED_TEMPLATE_NAME
        ),
        None,
    )
    if (
        len(field_names) != len(OWNED_FIELDS)
        or set(field_names) != OWNED_FIELDS
        or OWNED_MARKER not in str(model.get("css") or "")
        or owned_template is None
        or OWNED_MARKER not in str(owned_template.get("qfmt") or "")
        or OWNED_MARKER not in str(owned_template.get("afmt") or "")
    ):
        raise Exception(
            "The reserved recall note type is not the exact app-owned version."
        )

    target_index = field_names.index(fieldName)
    previous_index = int(models.sort_idx(model))
    if previous_index != target_index:
        models.set_sort_index(model, target_index)
        models.update_dict(model)

    verified = models.by_name(modelName)
    verified_index = int(models.sort_idx(verified))
    if verified_index != target_index:
        raise Exception("Anki did not save the requested sort field.")

    return {
        "changed": previous_index != target_index,
        "previousIndex": previous_index,
        "sortIndex": verified_index,
        "sortField": fieldName,
    }


def _install_api_action():
    anki_connect = importlib.import_module("2055492159")
    api_method = anki_connect.util.api()(_model_field_set_sort)
    setattr(
        anki_connect.AnkiConnect,
        "modelFieldSetSort",
        api_method,
    )


_install_api_action()
