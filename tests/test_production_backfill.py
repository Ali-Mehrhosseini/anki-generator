import base64
import copy
import tempfile
import unittest
from pathlib import Path

from main import build_manual_audio_html
from production_backfill import (
    BackfillSafetyError,
    OWNED_FIELDS,
    OWNED_MODEL_CSS,
    OWNED_MODEL_NAME,
    OWNED_TEMPLATE_BACK,
    OWNED_TEMPLATE_BACK_LEGACY,
    OWNED_TEMPLATE_FRONT,
    OWNED_TEMPLATE_NAME,
    apply_manifest,
    apply_rollback,
    atomic_write_manifest,
    discover_candidates,
    inspect_owned_model,
    inspect_owned_model_sort_field,
    inspect_rollback,
    load_manifest,
    manifest_lock,
    prepare_manifest,
    set_owned_model_sort_field,
)


class FakeAnki:
    def __init__(self):
        self.calls = []
        self.models = {
            "Italian Vocab": {
                "id": 1,
                "fields": [
                    "Word",
                    "Front",
                    "Back",
                    "WordAudio",
                    "Audio",
                    "Conjugation",
                    "AG_ProductionFront_v1",
                    "AG_ProductionBack_v1",
                ],
                "templates": {
                    "Card 1": {
                        "Front": "{{Front}}",
                        "Back": "{{FrontSide}}<hr>{{Back}}",
                    },
                },
                "css": ".card {}",
            },
        }
        self.notes = {
            101: {
                "noteId": 101,
                "profile": "Test",
                "tags": ["original"],
                "fields": self._fields({
                    "Word": "rispettare",
                    "Front": "<div>rispettare</div>",
                    "Back": "<div>to respect</div>",
                    "WordAudio": "[sound:rispettare.mp3]",
                    "Audio": "",
                    "Conjugation": "io rispetto",
                    "AG_ProductionFront_v1": "",
                    "AG_ProductionBack_v1": "",
                }),
                "modelName": "Italian Vocab",
                "mod": 100,
                "cards": [201],
            },
        }
        self.cards = {
            201: {
                "cardId": 201,
                "note": 101,
                "ord": 0,
                "fieldOrder": 0,
                "deckName": "Italian",
                "modelName": "Italian Vocab",
                "factor": 2500,
                "interval": 42,
                "type": 2,
                "queue": 2,
                "due": 1000,
                "reps": 18,
                "lapses": 1,
                "left": 0,
                "mod": 90,
                "flags": 0,
            },
        }
        self.reviews = {
            201: [
                {
                    "id": 1,
                    "usn": 0,
                    "ease": 3,
                    "ivl": 42,
                    "lastIvl": 20,
                    "factor": 2500,
                    "time": 900,
                    "type": 1,
                },
            ],
        }
        self.media = {}
        self.next_note_id = 1001
        self.next_card_id = 3001

    @staticmethod
    def _fields(values):
        return {
            name: {"value": value, "order": index}
            for index, (name, value) in enumerate(values.items())
        }

    def _owned_note_ids(self):
        return [
            note_id
            for note_id, note in self.notes.items()
            if note["modelName"] == OWNED_MODEL_NAME
        ]

    def __call__(self, action, params=None):
        params = copy.deepcopy(params or {})
        self.calls.append((action, params))

        if action == "modelNamesAndIds":
            return {
                name: model["id"]
                for name, model in self.models.items()
            }
        if action == "modelFieldNames":
            return list(self.models[params["modelName"]]["fields"])
        if action == "modelTemplates":
            return copy.deepcopy(
                self.models[params["modelName"]]["templates"]
            )
        if action == "modelStyling":
            return {"css": self.models[params["modelName"]]["css"]}
        if action == "findModelsByName":
            result = []
            for name in params["modelNames"]:
                model = self.models[name]
                result.append({
                    "id": model["id"],
                    "name": name,
                    "sortf": model.get("sortf", 0),
                    "flds": [
                        {"name": field_name, "ord": index}
                        for index, field_name in enumerate(model["fields"])
                    ],
                })
            return result
        if action == "modelFieldSetSort":
            model = self.models[params["modelName"]]
            previous = model.get("sortf", 0)
            target = model["fields"].index(params["fieldName"])
            model["sortf"] = target
            return {
                "changed": previous != target,
                "previousIndex": previous,
                "sortIndex": target,
                "sortField": params["fieldName"],
            }
        if action == "modelFieldReposition":
            fields = self.models[params["modelName"]]["fields"]
            field_name = params["fieldName"]
            fields.remove(field_name)
            fields.insert(params["index"], field_name)
            return None
        if action == "createModel":
            name = params["modelName"]
            self.models[name] = {
                "id": 2,
                "fields": list(params["inOrderFields"]),
                "templates": {
                    template["Name"]: {
                        "Front": template["Front"],
                        "Back": template["Back"],
                    }
                    for template in params["cardTemplates"]
                },
                "css": params["css"],
            }
            return {"id": 2}
        if action == "findNotes":
            query = params["query"]
            if query.startswith("tag:"):
                tag = query[len("tag:"):]
                return [
                    note_id
                    for note_id, note in self.notes.items()
                    if tag in note.get("tags", [])
                ]
            if 'deck:"Italian"' in query and 'note:"Italian Vocab"' in query:
                return [
                    note_id
                    for note_id, note in self.notes.items()
                    if note["modelName"] == "Italian Vocab"
                    and any(
                        self.cards[card_id]["deckName"] == "Italian"
                        for card_id in note["cards"]
                    )
                ]
            if query.startswith('note:"') and query.endswith('"'):
                model_name = query[len('note:"'):-1]
                return [
                    note_id
                    for note_id, note in self.notes.items()
                    if note["modelName"] == model_name
                ]
            return []
        if action == "notesInfo":
            return [
                copy.deepcopy(self.notes.get(int(note_id), {}))
                for note_id in params["notes"]
            ]
        if action == "cardsInfo":
            return [
                copy.deepcopy(self.cards.get(int(card_id), {}))
                for card_id in params["cards"]
            ]
        if action == "getReviewsOfCards":
            return {
                str(card_id): copy.deepcopy(
                    self.reviews.get(int(card_id), [])
                )
                for card_id in params["cards"]
            }
        if action == "exportPackage":
            Path(params["path"]).write_bytes(b"scheduled-backup")
            return True
        if action == "retrieveMediaFile":
            value = self.media.get(params["filename"])
            if value is None:
                return False
            return base64.b64encode(value).decode("ascii")
        if action == "storeMediaFile":
            filename = params["filename"]
            if filename in self.media and not params.get(
                "deleteExisting", True
            ):
                raise RuntimeError("media collision")
            self.media[filename] = base64.b64decode(params["data"])
            return filename
        if action == "createDeck":
            return 99
        if action == "addNote":
            payload = params["note"]
            note_id = self.next_note_id
            card_id = self.next_card_id
            self.next_note_id += 1
            self.next_card_id += 1
            fields = {
                name: payload["fields"].get(name, "")
                for name in self.models[payload["modelName"]]["fields"]
            }
            self.notes[note_id] = {
                "noteId": note_id,
                "profile": "Test",
                "tags": list(payload["tags"]),
                "fields": self._fields(fields),
                "modelName": payload["modelName"],
                "mod": 101,
                "cards": [card_id],
            }
            self.cards[card_id] = {
                "cardId": card_id,
                "note": note_id,
                "ord": 0,
                "fieldOrder": 0,
                "deckName": payload["deckName"],
                "modelName": payload["modelName"],
                "factor": 0,
                "interval": 0,
                "type": 0,
                "queue": 0,
                "due": 1,
                "reps": 0,
                "lapses": 0,
                "left": 0,
                "mod": 101,
                "flags": 0,
            }
            return note_id
        if action == "deleteNotes":
            for note_id in params["notes"]:
                note = self.notes.pop(int(note_id), None)
                if note:
                    for card_id in note["cards"]:
                        self.cards.pop(card_id, None)
            return None
        raise AssertionError(f"Unexpected Anki action: {action} {params}")


def fake_generate_content(
    word,
    language,
    api_key,
    custom_prompt=None,
    translation_lang=None,
    feature_options=None,
):
    control = build_manual_audio_html(
        word,
        "_example",
        f"Play {language} example",
        "anki-generator-production-example-audio",
    )
    return {
        "error": "",
        "word": word,
        "tts_example": "Bisogna rispettare le regole.",
        "production_card_html": {
            "front_html": "<div>to respect: Bisogna _____ le regole.</div>",
            "back_html": f"<div>rispettare</div>{control}",
        },
    }


class ProductionBackfillTests(unittest.TestCase):
    def test_preview_is_read_only_and_skips_existing_same_note_card(self):
        fake = FakeAnki()
        preview = discover_candidates(
            fake,
            "Italian",
            "Italian Vocab",
        )
        self.assertEqual(preview["eligible_total"], 1)
        mutating = {
            "addNote",
            "deleteNotes",
            "updateNoteFields",
            "createModel",
            "storeMediaFile",
            "modelFieldAdd",
            "modelTemplateAdd",
        }
        self.assertFalse(
            mutating.intersection(action for action, _ in fake.calls)
        )

        fake.notes[101]["fields"][
            "AG_ProductionFront_v1"
        ]["value"] = "already populated"
        preview = discover_candidates(
            fake,
            "Italian",
            "Italian Vocab",
        )
        self.assertEqual(preview["eligible_total"], 0)
        self.assertEqual(preview["already_same_note"], [101])

    def test_foreign_reserved_model_fails_closed(self):
        fake = FakeAnki()
        fake.models[OWNED_MODEL_NAME] = {
            "id": 2,
            "fields": ["Front"],
            "templates": {"Card 1": {"Front": "x", "Back": "y"}},
            "css": ".card {}",
        }
        with self.assertRaises(BackfillSafetyError):
            inspect_owned_model(fake)
        self.assertNotIn(
            "createModel",
            [action for action, _ in fake.calls],
        )

    def test_recall_sort_field_can_change_and_revert(self):
        fake = FakeAnki()
        fake.models[OWNED_MODEL_NAME] = {
            "id": 2,
            "fields": [
                "AG_SourceNoteID",
                "AG_RunID",
                "Word",
                "ProductionFront",
                "ProductionBack",
                "WordAudio",
            ],
            "templates": {
                OWNED_TEMPLATE_NAME: {
                    "Front": OWNED_TEMPLATE_FRONT,
                    "Back": OWNED_TEMPLATE_BACK,
                },
            },
            "css": OWNED_MODEL_CSS,
            "sortf": 0,
        }

        initial = inspect_owned_model_sort_field(fake)
        self.assertEqual(initial["sort_field"], "AG_SourceNoteID")

        changed = set_owned_model_sort_field(fake, "Word")
        self.assertTrue(changed["changed"])
        self.assertEqual(
            inspect_owned_model_sort_field(fake)["sort_field"],
            "Word",
        )

        reverted = set_owned_model_sort_field(
            fake,
            "AG_SourceNoteID",
        )
        self.assertTrue(reverted["changed"])
        self.assertEqual(
            inspect_owned_model_sort_field(fake)["sort_field"],
            "AG_SourceNoteID",
        )

    def test_apply_and_rollback_never_mutate_source_note(self):
        fake = FakeAnki()
        original_note = copy.deepcopy(fake.notes[101])
        original_card = copy.deepcopy(fake.cards[201])
        original_reviews = copy.deepcopy(fake.reviews[201])

        discovery = discover_candidates(
            fake,
            "Italian",
            "Italian Vocab",
        )
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            manifest_path = prepare_manifest(
                fake,
                workspace,
                "Italian",
                "Italian Vocab",
                "Italian",
                "Both (English + Persian)",
                discovery,
                destination_deck="Italian::Production Recall",
            )
            result = apply_manifest(
                fake,
                manifest_path,
                gemini_api_key="gemini",
                aws_access_key="access",
                aws_secret_key="secret",
                generate_content=fake_generate_content,
                create_polly_client=lambda *_: object(),
                generate_audio=lambda *_, **__: b"new-example-audio",
                language_configs={
                    "Italian": {
                        "voice": "Beatrice",
                        "code": "it-IT",
                        "engine": "generative",
                    },
                },
            )
            self.assertEqual(result["verified"], 1)
            self.assertEqual(result["remaining"], 0)
            self.assertEqual(fake.notes[101], original_note)
            self.assertEqual(fake.cards[201], original_card)
            self.assertEqual(fake.reviews[201], original_reviews)

            mutation_actions = [
                action
                for action, _ in fake.calls
                if action in {
                    "updateNoteFields",
                    "updateNote",
                    "updateModelTemplates",
                    "updateModelStyling",
                    "modelFieldAdd",
                    "modelFieldRemove",
                    "modelTemplateAdd",
                    "modelTemplateRemove",
                }
            ]
            self.assertEqual(mutation_actions, [])
            self.assertIn("createModel", [a for a, _ in fake.calls])
            self.assertIn("addNote", [a for a, _ in fake.calls])
            add_note_calls = [
                params
                for action, params in fake.calls
                if action == "addNote"
            ]
            self.assertTrue(
                add_note_calls[-1]["note"]["options"]["allowDuplicate"]
            )

            manifest = load_manifest(manifest_path)
            item = manifest["items"][0]
            created_note_id = item["created_note_id"]
            created_note = fake.notes[created_note_id]
            self.assertEqual(
                created_note["modelName"],
                OWNED_MODEL_NAME,
            )
            self.assertEqual(
                created_note["fields"]["AG_SourceNoteID"]["value"],
                "101",
            )
            self.assertEqual(
                fake.cards[created_note["cards"][0]]["deckName"],
                "Italian::Production Recall",
            )
            media_name = item["media_filename"]
            self.assertTrue(media_name.startswith("ag_prod_v1_"))
            self.assertEqual(
                fake.media[media_name],
                b"new-example-audio",
            )
            self.assertIn(
                media_name,
                created_note["fields"]["ProductionBack"]["value"],
            )
            self.assertNotIn(
                "rispettare_example.mp3",
                created_note["fields"]["ProductionBack"]["value"],
            )

            rollback_preview = inspect_rollback(
                fake,
                manifest_path,
            )
            self.assertEqual(
                rollback_preview["deletable"],
                [created_note_id],
            )
            rollback = apply_rollback(
                fake,
                workspace,
                manifest_path,
            )
            self.assertEqual(
                rollback["deleted_note_ids"],
                [created_note_id],
            )
            self.assertNotIn(created_note_id, fake.notes)
            self.assertEqual(fake.notes[101], original_note)
            self.assertEqual(fake.cards[201], original_card)
            self.assertEqual(fake.reviews[201], original_reviews)
            self.assertIn(media_name, fake.media)

    def test_rollback_refuses_edited_recall_note_without_force(self):
        fake = FakeAnki()
        discovery = discover_candidates(
            fake,
            "Italian",
            "Italian Vocab",
        )
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            manifest_path = prepare_manifest(
                fake,
                workspace,
                "Italian",
                "Italian Vocab",
                "Italian",
                "English",
                discovery,
            )
            apply_manifest(
                fake,
                manifest_path,
                gemini_api_key="gemini",
                aws_access_key="access",
                aws_secret_key="secret",
                generate_content=fake_generate_content,
                create_polly_client=lambda *_: object(),
                generate_audio=lambda *_, **__: b"audio",
                language_configs={
                    "Italian": {
                        "voice": "Beatrice",
                        "code": "it-IT",
                        "engine": "generative",
                    },
                },
            )
            manifest = load_manifest(manifest_path)
            note_id = manifest["items"][0]["created_note_id"]
            fake.notes[note_id]["fields"][
                "ProductionFront"
            ]["value"] = "user edit"

            preview = inspect_rollback(fake, manifest_path)
            self.assertEqual(preview["deletable"], [])
            self.assertEqual(len(preview["conflicts"]), 1)
            with self.assertRaises(BackfillSafetyError):
                apply_rollback(fake, workspace, manifest_path)
            self.assertIn(note_id, fake.notes)
            self.assertIn(101, fake.notes)

    def test_owned_model_contract_is_exact(self):
        fake = FakeAnki()
        fake.models[OWNED_MODEL_NAME] = {
            "id": 2,
            "fields": list(OWNED_FIELDS),
            "templates": {
                OWNED_TEMPLATE_NAME: {
                    "Front": OWNED_TEMPLATE_FRONT,
                    "Back": OWNED_TEMPLATE_BACK,
                },
            },
            "css": OWNED_MODEL_CSS,
        }
        result = inspect_owned_model(fake)
        self.assertTrue(result["exists"])
        self.assertEqual(result["model_id"], 2)

    def test_known_legacy_owned_template_is_safe_to_upgrade(self):
        fake = FakeAnki()
        fake.models[OWNED_MODEL_NAME] = {
            "id": 2,
            "fields": list(OWNED_FIELDS),
            "templates": {
                OWNED_TEMPLATE_NAME: {
                    "Front": OWNED_TEMPLATE_FRONT,
                    "Back": OWNED_TEMPLATE_BACK_LEGACY,
                },
            },
            "css": OWNED_MODEL_CSS,
        }

        result = inspect_owned_model(fake)

        self.assertTrue(result["exists"])
        self.assertFalse(result["template_current"])

    def test_corrupt_backup_blocks_apply_before_anki_mutation(self):
        fake = FakeAnki()
        discovery = discover_candidates(
            fake,
            "Italian",
            "Italian Vocab",
        )
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            manifest_path = prepare_manifest(
                fake,
                workspace,
                "Italian",
                "Italian Vocab",
                "Italian",
                "English",
                discovery,
            )
            manifest = load_manifest(manifest_path)
            Path(manifest["backup"]["path"]).write_bytes(b"corrupt")
            call_index = len(fake.calls)
            with self.assertRaises(BackfillSafetyError):
                apply_manifest(
                    fake,
                    manifest_path,
                    gemini_api_key="gemini",
                    aws_access_key="access",
                    aws_secret_key="secret",
                    generate_content=fake_generate_content,
                    create_polly_client=lambda *_: object(),
                    generate_audio=lambda *_, **__: b"audio",
                    language_configs={
                        "Italian": {
                            "voice": "Beatrice",
                            "code": "it-IT",
                            "engine": "generative",
                        },
                    },
                )
            writes = {
                action
                for action, _ in fake.calls[call_index:]
                if action in {
                    "createModel",
                    "storeMediaFile",
                    "addNote",
                    "deleteNotes",
                }
            }
            self.assertEqual(writes, set())

    def test_rollback_recovers_note_created_before_id_was_journaled(self):
        fake = FakeAnki()
        discovery = discover_candidates(
            fake,
            "Italian",
            "Italian Vocab",
        )
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            manifest_path = prepare_manifest(
                fake,
                workspace,
                "Italian",
                "Italian Vocab",
                "Italian",
                "English",
                discovery,
            )
            apply_manifest(
                fake,
                manifest_path,
                gemini_api_key="gemini",
                aws_access_key="access",
                aws_secret_key="secret",
                generate_content=fake_generate_content,
                create_polly_client=lambda *_: object(),
                generate_audio=lambda *_, **__: b"audio",
                language_configs={
                    "Italian": {
                        "voice": "Beatrice",
                        "code": "it-IT",
                        "engine": "generative",
                    },
                },
            )
            manifest = load_manifest(manifest_path)
            created_note_id = manifest["items"][0]["created_note_id"]
            manifest["items"][0].pop("created_note_id")
            manifest["items"][0].pop("created_card_ids")
            manifest["items"][0].pop("generated_note_fingerprint")
            manifest["items"][0]["stage"] = "media_stored"
            atomic_write_manifest(manifest_path, manifest)

            preview = inspect_rollback(fake, manifest_path)
            self.assertEqual(preview["deletable"], [created_note_id])
            self.assertEqual(
                preview["recovered"],
                [{"source_note_id": 101, "note_id": created_note_id}],
            )
            result = apply_rollback(
                fake,
                workspace,
                manifest_path,
            )
            self.assertEqual(
                result["deleted_note_ids"],
                [created_note_id],
            )
            self.assertNotIn(created_note_id, fake.notes)
            self.assertIn(101, fake.notes)

    def test_source_change_during_generation_never_creates_recall_note(self):
        fake = FakeAnki()
        discovery = discover_candidates(
            fake,
            "Italian",
            "Italian Vocab",
        )
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            manifest_path = prepare_manifest(
                fake,
                workspace,
                "Italian",
                "Italian Vocab",
                "Italian",
                "English",
                discovery,
            )

            def audio_with_concurrent_review(*args, **kwargs):
                fake.cards[201]["due"] += 1
                return b"audio"

            result = apply_manifest(
                fake,
                manifest_path,
                gemini_api_key="gemini",
                aws_access_key="access",
                aws_secret_key="secret",
                generate_content=fake_generate_content,
                create_polly_client=lambda *_: object(),
                generate_audio=audio_with_concurrent_review,
                language_configs={
                    "Italian": {
                        "voice": "Beatrice",
                        "code": "it-IT",
                        "engine": "generative",
                    },
                },
            )
            self.assertEqual(result["conflicts"], 1)
            self.assertEqual(fake._owned_note_ids(), [])
            self.assertNotIn(
                "addNote",
                [action for action, _ in fake.calls],
            )

    def test_audio_cache_makes_store_interruption_resumable(self):
        fake = FakeAnki()
        failed_once = {"value": False}

        def flaky_invoke(action, params=None):
            if action == "storeMediaFile" and not failed_once["value"]:
                failed_once["value"] = True
                fake(action, params)
                raise RuntimeError("connection lost after media write")
            return fake(action, params)

        discovery = discover_candidates(
            flaky_invoke,
            "Italian",
            "Italian Vocab",
        )
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            manifest_path = prepare_manifest(
                flaky_invoke,
                workspace,
                "Italian",
                "Italian Vocab",
                "Italian",
                "English",
                discovery,
            )
            first = apply_manifest(
                flaky_invoke,
                manifest_path,
                gemini_api_key="gemini",
                aws_access_key="access",
                aws_secret_key="secret",
                generate_content=fake_generate_content,
                create_polly_client=lambda *_: object(),
                generate_audio=lambda *_, **__: b"stable-audio",
                language_configs={
                    "Italian": {
                        "voice": "Beatrice",
                        "code": "it-IT",
                        "engine": "generative",
                    },
                },
            )
            self.assertEqual(first["remaining"], 1)
            manifest = load_manifest(manifest_path)
            self.assertEqual(manifest["items"][0]["stage"], "generated")
            self.assertTrue(
                Path(manifest["items"][0]["audio_cache_path"]).is_file()
            )

            second = apply_manifest(
                flaky_invoke,
                manifest_path,
                gemini_api_key=None,
                aws_access_key=None,
                aws_secret_key=None,
                generate_content=lambda *_, **__: self.fail(
                    "Gemini should not be called on resume"
                ),
                create_polly_client=lambda *_: self.fail(
                    "Polly client should not be recreated"
                ),
                generate_audio=lambda *_, **__: self.fail(
                    "Polly should not be called on resume"
                ),
                language_configs={
                    "Italian": {
                        "voice": "Beatrice",
                        "code": "it-IT",
                        "engine": "generative",
                    },
                },
            )
            self.assertEqual(second["verified"], 1)
            self.assertEqual(second["remaining"], 0)

    def test_rollback_backs_up_current_card_deck(self):
        fake = FakeAnki()
        discovery = discover_candidates(
            fake,
            "Italian",
            "Italian Vocab",
        )
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            manifest_path = prepare_manifest(
                fake,
                workspace,
                "Italian",
                "Italian Vocab",
                "Italian",
                "English",
                discovery,
            )
            apply_manifest(
                fake,
                manifest_path,
                gemini_api_key="gemini",
                aws_access_key="access",
                aws_secret_key="secret",
                generate_content=fake_generate_content,
                create_polly_client=lambda *_: object(),
                generate_audio=lambda *_, **__: b"audio",
                language_configs={
                    "Italian": {
                        "voice": "Beatrice",
                        "code": "it-IT",
                        "engine": "generative",
                    },
                },
            )
            manifest = load_manifest(manifest_path)
            card_id = manifest["items"][0]["created_card_ids"][0]
            fake.cards[card_id]["deckName"] = "Moved Recall Cards"
            preview = inspect_rollback(fake, manifest_path)
            self.assertEqual(
                preview["target_decks"],
                ["Moved Recall Cards"],
            )
            apply_rollback(fake, workspace, manifest_path)
            exported_decks = [
                params["deck"]
                for action, params in fake.calls
                if action == "exportPackage"
            ]
            self.assertIn("Moved Recall Cards", exported_decks)

    def test_resume_is_blocked_after_rollback_state_begins(self):
        fake = FakeAnki()
        discovery = discover_candidates(
            fake,
            "Italian",
            "Italian Vocab",
        )
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            manifest_path = prepare_manifest(
                fake,
                workspace,
                "Italian",
                "Italian Vocab",
                "Italian",
                "English",
                discovery,
            )
            manifest = load_manifest(manifest_path)
            manifest["state"] = "rolling_back"
            atomic_write_manifest(manifest_path, manifest)
            with self.assertRaises(BackfillSafetyError):
                apply_manifest(
                    fake,
                    manifest_path,
                    gemini_api_key="gemini",
                    aws_access_key="access",
                    aws_secret_key="secret",
                    generate_content=fake_generate_content,
                    create_polly_client=lambda *_: object(),
                    generate_audio=lambda *_, **__: b"audio",
                    language_configs={
                        "Italian": {
                            "voice": "Beatrice",
                            "code": "it-IT",
                            "engine": "generative",
                        },
                    },
                )

    def test_manifest_lock_blocks_concurrent_apply(self):
        fake = FakeAnki()
        discovery = discover_candidates(
            fake,
            "Italian",
            "Italian Vocab",
        )
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            manifest_path = prepare_manifest(
                fake,
                workspace,
                "Italian",
                "Italian Vocab",
                "Italian",
                "English",
                discovery,
            )
            with manifest_lock(manifest_path):
                with self.assertRaises(BackfillSafetyError):
                    apply_manifest(
                        fake,
                        manifest_path,
                        gemini_api_key="gemini",
                        aws_access_key="access",
                        aws_secret_key="secret",
                        generate_content=fake_generate_content,
                        create_polly_client=lambda *_: object(),
                        generate_audio=lambda *_, **__: b"audio",
                        language_configs={
                            "Italian": {
                                "voice": "Beatrice",
                                "code": "it-IT",
                                "engine": "generative",
                            },
                        },
                    )

    def test_converted_recall_note_is_conflict_not_missing(self):
        fake = FakeAnki()
        discovery = discover_candidates(
            fake,
            "Italian",
            "Italian Vocab",
        )
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            manifest_path = prepare_manifest(
                fake,
                workspace,
                "Italian",
                "Italian Vocab",
                "Italian",
                "English",
                discovery,
            )
            apply_manifest(
                fake,
                manifest_path,
                gemini_api_key="gemini",
                aws_access_key="access",
                aws_secret_key="secret",
                generate_content=fake_generate_content,
                create_polly_client=lambda *_: object(),
                generate_audio=lambda *_, **__: b"audio",
                language_configs={
                    "Italian": {
                        "voice": "Beatrice",
                        "code": "it-IT",
                        "engine": "generative",
                    },
                },
            )
            manifest = load_manifest(manifest_path)
            note_id = manifest["items"][0]["created_note_id"]
            card_id = manifest["items"][0]["created_card_ids"][0]
            fake.notes[note_id]["modelName"] = "Italian Vocab"
            fake.cards[card_id]["modelName"] = "Italian Vocab"

            preview = inspect_rollback(fake, manifest_path)
            self.assertEqual(preview["deletable"], [])
            self.assertTrue(preview["conflicts"])
            self.assertNotIn(note_id, preview["already_missing"])

    def test_renamed_owned_model_still_prevents_duplicate_backfill(self):
        fake = FakeAnki()
        discovery = discover_candidates(
            fake,
            "Italian",
            "Italian Vocab",
        )
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            manifest_path = prepare_manifest(
                fake,
                workspace,
                "Italian",
                "Italian Vocab",
                "Italian",
                "English",
                discovery,
            )
            apply_manifest(
                fake,
                manifest_path,
                gemini_api_key="gemini",
                aws_access_key="access",
                aws_secret_key="secret",
                generate_content=fake_generate_content,
                create_polly_client=lambda *_: object(),
                generate_audio=lambda *_, **__: b"audio",
                language_configs={
                    "Italian": {
                        "voice": "Beatrice",
                        "code": "it-IT",
                        "engine": "generative",
                    },
                },
            )
            manifest = load_manifest(manifest_path)
            note_id = manifest["items"][0]["created_note_id"]
            card_id = manifest["items"][0]["created_card_ids"][0]
            renamed = fake.models.pop(OWNED_MODEL_NAME)
            fake.models["Renamed Recall Model"] = renamed
            fake.notes[note_id]["modelName"] = "Renamed Recall Model"
            fake.cards[card_id]["modelName"] = "Renamed Recall Model"

            next_preview = discover_candidates(
                fake,
                "Italian",
                "Italian Vocab",
            )
            self.assertEqual(next_preview["eligible_total"], 0)
            self.assertEqual(
                next_preview["already_backfilled"],
                [{
                    "source_note_id": 101,
                    "recall_note_ids": [note_id],
                }],
            )
            rollback_preview = inspect_rollback(
                fake,
                manifest_path,
            )
            self.assertEqual(
                rollback_preview["deletable"],
                [note_id],
            )
            apply_rollback(fake, workspace, manifest_path)
            self.assertNotIn(note_id, fake.notes)
            self.assertIn(101, fake.notes)

    def test_empty_rollback_seals_manifest_against_resume(self):
        fake = FakeAnki()
        discovery = discover_candidates(
            fake,
            "Italian",
            "Italian Vocab",
        )
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            manifest_path = prepare_manifest(
                fake,
                workspace,
                "Italian",
                "Italian Vocab",
                "Italian",
                "English",
                discovery,
            )
            result = apply_rollback(
                fake,
                workspace,
                manifest_path,
            )
            self.assertEqual(result["deleted_note_ids"], [])
            self.assertEqual(
                load_manifest(manifest_path)["state"],
                "rolled_back",
            )
            with self.assertRaises(BackfillSafetyError):
                apply_manifest(
                    fake,
                    manifest_path,
                    gemini_api_key="gemini",
                    aws_access_key="access",
                    aws_secret_key="secret",
                    generate_content=fake_generate_content,
                    create_polly_client=lambda *_: object(),
                    generate_audio=lambda *_, **__: b"audio",
                    language_configs={
                        "Italian": {
                            "voice": "Beatrice",
                            "code": "it-IT",
                            "engine": "generative",
                        },
                    },
                )


if __name__ == "__main__":
    unittest.main()
