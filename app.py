import base64
import hashlib
import json
import os
import re
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory
from dotenv import load_dotenv

from main import (
    process_word,
    generate_practice_feedback,
    transcribe_practice_audio,
    generate_practice_audio_feedback,
    generate_grammar_explanation,
    generate_word_help,
    generate_word_usage_help,
    generate_word_mnemonic,
    generate_dictogloss_text,
    generate_dictogloss_feedback,
    process_grammar_card,
    generate_grammar_transfer_feedback,
    generate_grammar_conversation_feedback,
    get_grammar_topics_by_level,
    get_grammar_topics_by_mode,
    GRAMMAR_DECK_NAME,
    GRAMMAR_NOTE_TYPE,
    GRAMMAR_FIELDS,
    GRAMMAR_TEMPLATE_NAME,
    GRAMMAR_TEMPLATE_FRONT,
    GRAMMAR_TEMPLATE_BACK,
    GRAMMAR_CONTRAST_TOPICS,
    GRAMMAR_MISTAKE_TOPICS,
    GRAMMAR_TOPICS,
    LANGUAGE_CONFIGS,
    _resolve_grammar_topic,
    generate_audio,
    format_polly_error,
)
from learning_lab import (
    build_session,
    load_state,
    record_session,
    record_word_help,
    save_state,
    transcript_plausibility_problem,
)
from cli import invoke_anki, ensure_grammar_model_and_deck, check_grammar_duplicate
from grammar_practice import (
    anki_metadata_fields,
    backfill_legacy_metadata,
    check_controlled_answer,
    create_dictogloss_session,
    create_session as create_grammar_practice_session,
    dictogloss_session,
    list_conversation_scenarios,
    mastery_by_topic,
    practice_overview,
    record_conversation_result,
    record_dictogloss_result,
    record_transfer_result,
    session_conversation_context,
    session_item_context,
    session_summary,
    session_transfer_context,
)
from error_insights import collect_errors, recommend_topics

PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / '.env')

app = Flask(__name__, static_folder='static', static_url_path='')

# (audio data key suffix -> media filename suffix) per grammar mode.
GRAMMAR_AUDIO_SUFFIXES = {
    "contrast": (("senta", "senta"), ("sentb", "sentb")),
    "mistake": (("corrected", "corr"),),
    "input": (("sentence", "sent"),),
}
GRAMMAR_AUDIO_DEFAULT = (("answer", "ans"), ("sentence", "sent"))


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/settings')
def settings():
    return send_from_directory('static', 'settings.html')

@app.route('/speaking')
def speaking():
    return send_from_directory('static', 'speaking.html')


@app.route('/api/prompt', methods=['GET'])
def get_prompt():
    from main import SYSTEM_INSTRUCTION_TEMPLATE
    prompt_version = hashlib.sha256(SYSTEM_INSTRUCTION_TEMPLATE.encode('utf-8')).hexdigest()
    return jsonify({"prompt": SYSTEM_INSTRUCTION_TEMPLATE, "version": prompt_version}), 200

@app.route('/api/verify-keys', methods=['POST'])
def verify_keys():
    from main import verify_api_keys
    data = request.json
    api_keys = data.get('apiKeys', {})
    gemini_key = api_keys.get('gemini', '')
    aws_access = api_keys.get('aws_access', '')
    aws_secret = api_keys.get('aws_secret', '')

    result = verify_api_keys(gemini_key, aws_access, aws_secret)
    return jsonify(result), 200

@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.json
    word = data.get('word')
    language = data.get('language', 'Italian')
    custom_prompt = data.get('prompt')
    translation_lang = data.get('translationLang', 'Both (English + Persian)')
    feature_options = data.get('features')
    selected_interpretation = data.get('selectedInterpretation')
    api_keys = data.get('apiKeys', {})

    if not word:
        return Response(
            f"data: {json.dumps({'error': 'No word provided'})}\n\n",
            mimetype='text/event-stream',
        )

    return Response(
        process_word(
            word,
            language=language,
            api_keys=api_keys,
            custom_prompt=custom_prompt,
            translation_lang=translation_lang,
            feature_options=feature_options,
            selected_interpretation=selected_interpretation,
        ),
        mimetype='text/event-stream',
        headers={
            'X-Accel-Buffering': 'no',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive'
        }
    )

@app.route('/api/learning-lab/session', methods=['POST'])
def learning_lab_session():
    try:
        data = request.json or {}
        state = load_state(PROJECT_DIR)
        session = build_session(
            invoke_anki,
            state,
            data.get('sourceModel', 'Italian Vocab'),
            data.get('recallModel', 'AG Production Recall v1'),
            count=1,
            ladder_level=data.get('ladderLevel', 1),
            exclude_words=data.get('excludeWords') or [],
        )
        if session.get('task'):
            try:
                grammar_mastery = mastery_by_topic(invoke_anki, PROJECT_DIR)
                session['task']['known_grammar_topics'] = [
                    {
                        'key': key,
                        'topic': value.get('topic') or key,
                        'status': value.get('status') or 'new',
                    }
                    for key, value in grammar_mastery.items()
                    if int(value.get('cards') or 0) > 0
                ]
            except Exception:
                session['task']['known_grammar_topics'] = []
        return jsonify(session), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 400

def _unreliable_transcript_response(feedback: dict, problem: str) -> dict:
    """Build the 'not graded' reply for a physically implausible transcript."""
    return {
        "overall_en": problem,
        "overall_fa": (
            "متن ثبت‌شده بسیار طولانی‌تر از صدای اندازه‌گیری‌شده است؛ "
            "این تلاش نمره‌گذاری یا شمرده نشد. دوباره ضبط کن."
        ),
        "evaluation_reliable": False,
        "transcript_it": str(feedback.get("transcript_it") or ""),
        "transcription_uncertain": True,
        "target_results": [],
        "not_graded": True,
    }


@app.route('/api/learning-lab/feedback', methods=['POST'])
def learning_lab_feedback():
    try:
        data = request.json or {}
        state = load_state(PROJECT_DIR)
        mode = 'voice' if data.get('mode') == 'voice' else 'text'
        transcript_text = str(data.get('response') or '')
        fluency = data.get('fluency') or {}
        duration = data.get('durationSeconds', 0)
        problem = transcript_plausibility_problem(
            transcript_text, fluency, duration
        )
        if problem:
            return jsonify(
                _unreliable_transcript_response(
                    {"transcript_it": transcript_text}, problem
                )
            ), 200
        feedback = generate_practice_feedback(
            data.get('targets') or [],
            data.get('task') or {},
            transcript_text,
            str(data.get('geminiKey') or os.getenv('GEMINI_API_KEY') or ''),
            response_mode=mode,
        )
        if feedback.get('error'):
            return jsonify(feedback), 400
        record_session(
            state,
            data.get('targets') or [],
            response=transcript_text,
            feedback=feedback,
            mode=mode,
            duration_seconds=duration,
            attempt=data.get('attempt', 1),
            round_number=data.get('round', 1),
            phase=data.get('phase', 'translation'),
            fluency=fluency,
            evaluation_reliable=bool(feedback.get('evaluation_reliable', True)),
        )
        save_state(PROJECT_DIR, state)
        return jsonify(feedback), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 400


@app.route('/api/learning-lab/transcribe', methods=['POST'])
def learning_lab_transcribe():
    """Fallback for browsers whose live speech recognizer returns no text."""
    try:
        upload = request.files.get('audio')
        if upload is None:
            return jsonify({"error": "No recording was received."}), 400
        audio = upload.read(5 * 1024 * 1024 + 1)
        transcript = transcribe_practice_audio(
            audio,
            upload.mimetype or 'audio/webm',
            str(request.form.get('geminiKey') or os.getenv('GEMINI_API_KEY') or ''),
        )
        return jsonify({"transcript": transcript}), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 400


@app.route('/api/learning-lab/audio-feedback', methods=['POST'])
def learning_lab_audio_feedback():
    """Evaluate temporary audio directly when the browser transcript is absent."""
    try:
        upload = request.files.get('audio')
        if upload is None:
            return jsonify({"error": "No recording was received."}), 400
        context = json.loads(request.form.get('context') or '{}')
        audio = upload.read(5 * 1024 * 1024 + 1)
        feedback = generate_practice_audio_feedback(
            audio,
            upload.mimetype or 'audio/webm',
            context.get('targets') or [],
            context.get('task') or {},
            str(request.form.get('geminiKey') or os.getenv('GEMINI_API_KEY') or ''),
        )
        # Hallucination gate: Gemini sees the model sentence, so a clip with a
        # breath or two spoken words can come back "transcribed" as the whole
        # answer. Measured voice time must plausibly cover the transcript —
        # otherwise nothing is recorded and nothing is graded.
        problem = transcript_plausibility_problem(
            feedback.get('transcript_it') or '',
            context.get('fluency') or {},
            context.get('durationSeconds', 0),
        )
        if problem:
            return jsonify(
                _unreliable_transcript_response(feedback, problem)
            ), 200
        state = load_state(PROJECT_DIR)
        record_session(
            state,
            context.get('targets') or [],
            response=feedback.get('transcript_it', ''),
            feedback=feedback,
            mode='voice',
            duration_seconds=context.get('durationSeconds', 0),
            attempt=context.get('attempt', 1),
            round_number=context.get('round', 1),
            phase=context.get('phase', 'translation'),
            fluency=context.get('fluency') or {},
            evaluation_reliable=bool(feedback.get('evaluation_reliable', True)),
        )
        save_state(PROJECT_DIR, state)
        return jsonify(feedback), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 400


@app.route('/api/learning-lab/word-help', methods=['POST'])
def learning_lab_word_help():
    """Hint-ladder help for one English word, plus lookup tracking.

    recordOnly=True skips Gemini and only stores the guess/reveal/add event;
    the help fetch itself is recorded as a peek.
    """
    try:
        data = request.json or {}
        word = str(data.get('word') or '').strip()
        if not word or len(word) > 60:
            return jsonify({"error": "No valid word was provided."}), 400
        event = str(data.get('event') or 'peek').strip()
        state = load_state(PROJECT_DIR)
        if data.get('recordOnly'):
            record_word_help(
                state,
                word,
                event,
                guessed_correctly=data.get('guessedCorrectly'),
            )
            save_state(PROJECT_DIR, state)
            return jsonify({"ok": True}), 200
        if data.get('deep'):
            # Contextual why-this-word / why-this-form explanation. Loads in
            # parallel with the fast hint and is never recorded as a lookup.
            return jsonify(generate_word_usage_help(
                word,
                str(data.get('lemma') or '')[:60],
                str(data.get('context') or '')[:300],
                str(data.get('startingIt') or '')[:200],
                str(data.get('geminiKey') or os.getenv('GEMINI_API_KEY') or ''),
            )), 200
        if data.get('mnemonic'):
            # Keyword-method memory trick for an already-revealed word.
            return jsonify(generate_word_mnemonic(
                word,
                str(data.get('meaning') or '')[:200],
                str(data.get('geminiKey') or os.getenv('GEMINI_API_KEY') or ''),
            )), 200
        result = generate_word_help(
            word,
            str(data.get('context') or '')[:300],
            str(data.get('geminiKey') or os.getenv('GEMINI_API_KEY') or ''),
        )
        if result.get('error'):
            return jsonify(result), 400
        if event in ('peek', 'reveal'):
            record_word_help(state, word, event)
            save_state(PROJECT_DIR, state)
        return jsonify(result), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 400


@app.route('/api/learning-lab/polly', methods=['POST'])
def learning_lab_polly():
    """Speak one short corrected Italian sentence without storing the audio."""
    try:
        data = request.json or {}
        sentence = str(data.get('sentence') or '').strip()
        if not sentence:
            return jsonify({"error": "No Italian sentence was provided."}), 400
        if len(sentence) > 500:
            return jsonify({"error": "The Italian sentence is too long."}), 400
        keys = data.get('apiKeys') or {}
        voice_options = {
            'Beatrice': 'generative',
            'Bianca': 'generative',
            'Lorenzo': 'generative',
        }
        voice = str(data.get('voice') or 'Beatrice')
        if voice not in voice_options:
            return jsonify({"error": "Unsupported Italian voice."}), 400
        audio = generate_audio(
            sentence,
            voice,
            'it-IT',
            str(keys.get('aws_access') or os.getenv('AWS_ACCESS_KEY') or ''),
            str(keys.get('aws_secret') or os.getenv('AWS_SECRET_KEY') or ''),
            engine=voice_options[voice],
        )
        return Response(
            audio,
            mimetype='audio/mpeg',
            headers={'Cache-Control': 'no-store'},
        )
    except Exception as error:
        return jsonify({"error": format_polly_error(error)}), 400

# ---------------------------------------------------------------------------
# Grammar routes
# ---------------------------------------------------------------------------

@app.route('/grammar')
def grammar():
    return send_from_directory('static', 'grammar.html')

@app.route('/api/grammar/generate', methods=['POST'])
def grammar_generate():
    data = request.json or {}
    topic = data.get('topic', '')
    api_keys = data.get('apiKeys', {})
    mode = data.get('mode', 'standard')

    if not topic:
        return Response(
            f"data: {json.dumps({'error': 'No grammar topic provided'})}\n\n",
            mimetype='text/event-stream',
        )

    return Response(
        process_grammar_card(topic, api_keys=api_keys, mode=mode),
        mimetype='text/event-stream',
        headers={
            'X-Accel-Buffering': 'no',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
        },
    )

@app.route('/api/grammar/topics', methods=['GET'])
def grammar_topics():
    mode = request.args.get('mode', 'standard')
    level = request.args.get('level')
    topics = get_grammar_topics_by_mode(mode, level)

    try:
        mastery = mastery_by_topic(invoke_anki, PROJECT_DIR)
    except Exception:
        mastery = {}

    # Error-driven recommendations use every catalog so a pronoun slip in the
    # Speaking Lab can recommend, say, a contrast topic.
    recommendations = {}
    try:
        insights = collect_errors(PROJECT_DIR)
        recommendations = {
            entry["topic_key"]: entry
            for entry in recommend_topics(
                insights["patterns"],
                {
                    "standard": GRAMMAR_TOPICS,
                    "contrast": GRAMMAR_CONTRAST_TOPICS,
                    "mistake": GRAMMAR_MISTAKE_TOPICS,
                },
                mastery=mastery,
            )
        }
    except Exception:
        recommendations = {}

    # Existence and mastery are intentionally separate.
    for lvl, topic_list in topics.items():
        for topic in topic_list:
            try:
                topic['has_cards'] = check_grammar_duplicate(topic['title_it'])
            except Exception:
                topic['has_cards'] = False
            topic['mastery'] = mastery.get(topic['key'], {
                'score': 0,
                'status': 'new',
                'cards': 0,
                'controlled_attempts': 0,
                'transfer_attempts': 0,
                'speaking_attempts': 0,
                'stages': {
                    'recognition': 0,
                    'input': 0,
                    'controlled': 0,
                    'free': 0,
                    'speaking': 0,
                },
            })
            topic['completed'] = topic['mastery']['status'] == 'mastered'
            recommendation = recommendations.get(topic['key'])
            topic['recommended'] = bool(recommendation)
            if recommendation:
                topic['recommendation_reason'] = (
                    f"Recurring {recommendation['error_type'].replace('_', ' ')} "
                    f"({recommendation['reason']})"
                )

    return jsonify(topics), 200


@app.route('/api/grammar/practice/session', methods=['POST'])
def grammar_practice_session():
    try:
        data = request.json or {}
        ensure_grammar_model_and_deck()
        backfill_legacy_metadata(invoke_anki, _resolve_grammar_topic)
        session = create_grammar_practice_session(
            invoke_anki,
            PROJECT_DIR,
            count=max(1, min(int(data.get('count') or 6), 12)),
        )
        return jsonify(session), 200
    except Exception as error:
        return jsonify({'error': str(error)}), 400


@app.route('/api/grammar/practice/overview', methods=['GET'])
def grammar_practice_overview():
    try:
        ensure_grammar_model_and_deck()
        backfill_legacy_metadata(invoke_anki, _resolve_grammar_topic)
        result = practice_overview(
            invoke_anki, PROJECT_DIR
        )
        return jsonify(result), 200
    except Exception as error:
        return jsonify({'error': str(error)}), 400


@app.route('/api/grammar/practice/check', methods=['POST'])
def grammar_practice_check():
    try:
        data = request.json or {}
        result = check_controlled_answer(
            PROJECT_DIR,
            str(data.get('sessionId') or ''),
            int(data.get('itemIndex')),
            [str(value) for value in (data.get('responses') or [])],
        )
        return jsonify(result), 200
    except Exception as error:
        return jsonify({'error': str(error)}), 400


@app.route('/api/grammar/practice/explain', methods=['POST'])
def grammar_practice_explain():
    """Explain the learner's mistake without revealing the correct answer."""
    try:
        data = request.json or {}
        api_keys = data.get('apiKeys') or {}
        if str(data.get('kind') or 'controlled') == 'transfer':
            transfer = session_transfer_context(
                PROJECT_DIR, str(data.get('sessionId') or '')
            )
            task = {
                'kind': 'transfer',
                'level': str(data.get('level') or 'A2'),
                'topic': ' / '.join(
                    str(topic.get('topic') or '')
                    for topic in (transfer.get('topics') or [])
                ),
                'rule_en': ' '.join(
                    str(topic.get('rule_en') or '')
                    for topic in (transfer.get('topics') or [])
                ),
                'rule_fa': ' '.join(
                    str(topic.get('rule_fa') or '')
                    for topic in (transfer.get('topics') or [])
                ),
                'prompt_en': transfer.get('prompt_en') or '',
                'topics': transfer.get('topics') or [],
                'learner_response': str(data.get('response') or ''),
            }
        else:
            task = session_item_context(
                PROJECT_DIR,
                str(data.get('sessionId') or ''),
                int(data.get('itemIndex')),
                [str(value) for value in (data.get('responses') or [])],
            )
        result = generate_grammar_explanation(
            task,
            str(api_keys.get('gemini') or ''),
        )
        if result.get('error'):
            return jsonify(result), 400
        return jsonify(result), 200
    except Exception as error:
        return jsonify({'error': str(error)}), 400


@app.route('/api/grammar/practice/transfer-feedback', methods=['POST'])
def grammar_practice_transfer_feedback():
    try:
        data = request.json or {}
        session_id = str(data.get('sessionId') or '')
        response_text = str(data.get('response') or '')
        api_keys = data.get('apiKeys') or {}
        stage = str(data.get('stage') or 'free')
        if stage not in {'free', 'speaking'}:
            raise ValueError('Unsupported grammar production stage.')
        transfer = session_transfer_context(PROJECT_DIR, session_id)
        if stage == 'speaking':
            transfer = dict(transfer)
            transfer['prompt_en'] = (
                'This is a speech transcript. Evaluate target grammar only; '
                'do not penalize likely speech-recognition punctuation. '
                + str(transfer.get('prompt_en') or '')
            )
        feedback = generate_grammar_transfer_feedback(
            transfer,
            response_text,
            str(api_keys.get('gemini') or ''),
        )
        if feedback.get('error'):
            return jsonify(feedback), 400
        attempt = record_transfer_result(
            PROJECT_DIR, session_id, response_text, feedback, stage=stage
        )
        attempt_number = int(attempt.get('attempt_number') or 1)
        correct = bool(feedback.get('correct'))
        result = dict(feedback)
        result['attempt'] = attempt_number
        result['retry_required'] = not correct and attempt_number < 2
        result['can_continue'] = correct or attempt_number >= 2
        if result['retry_required']:
            result['corrected_response_it'] = ''
        return jsonify(result), 200
    except Exception as error:
        return jsonify({'error': str(error)}), 400


@app.route('/api/grammar/practice/scenarios', methods=['GET'])
def grammar_practice_scenarios():
    return jsonify(list_conversation_scenarios()), 200


@app.route('/api/grammar/practice/conversation-turn', methods=['POST'])
def grammar_practice_conversation_turn():
    try:
        data = request.json or {}
        session_id = str(data.get('sessionId') or '')
        response_text = str(data.get('response') or '')
        api_keys = data.get('apiKeys') or {}
        context = session_conversation_context(PROJECT_DIR, session_id)
        feedback = generate_grammar_conversation_feedback(
            context,
            response_text,
            str(api_keys.get('gemini') or ''),
        )
        if feedback.get('error'):
            return jsonify(feedback), 400
        previous_turns = context.get('turns') or []
        retrying = bool(
            previous_turns
            and not previous_turns[-1].get('correct')
            and (previous_turns[-1].get('feedback') or {}).get('retry_required')
        )
        correct = bool(feedback.get('correct'))
        feedback['retry_required'] = not correct and not retrying
        feedback['can_continue'] = correct or retrying
        completed_before = sum(
            bool((turn.get('feedback') or {}).get('can_continue'))
            for turn in previous_turns
        )
        feedback['complete'] = (
            completed_before + int(feedback['can_continue'])
            >= int(context.get('max_turns') or 3)
        )
        if feedback['retry_required']:
            feedback['corrected_response_it'] = ''
        turn = record_conversation_result(
            PROJECT_DIR, session_id, response_text, feedback
        )
        result = dict(feedback)
        result['turn'] = int(turn.get('turn_number') or 1)
        return jsonify(result), 200
    except Exception as error:
        return jsonify({'error': str(error)}), 400


@app.route('/api/grammar/practice/conversation', methods=['POST'])
def grammar_practice_conversation():
    try:
        data = request.json or {}
        result = session_conversation_context(
            PROJECT_DIR,
            str(data.get('sessionId') or ''),
            scenario_key=data.get('scenario') or None,
        )
        return jsonify(result), 200
    except Exception as error:
        return jsonify({'error': str(error)}), 400


@app.route('/api/grammar/practice/summary', methods=['POST'])
def grammar_practice_summary():
    try:
        data = request.json or {}
        result = session_summary(
            PROJECT_DIR,
            str(data.get('sessionId') or ''),
        )
        return jsonify(result), 200
    except Exception as error:
        return jsonify({'error': str(error)}), 400


@app.route('/api/grammar/dictogloss/text', methods=['POST'])
def grammar_dictogloss_text():
    """Generate a dictogloss text: audio returned, original stays server-side."""
    try:
        data = request.json or {}
        api_keys = data.get('apiKeys') or {}
        topic_input = str(data.get('topic') or '').strip()
        if not topic_input:
            return jsonify({'error': 'Choose a grammar topic first.'}), 400
        topic_key, topic_info = _resolve_grammar_topic(topic_input, mode='standard')
        topic = {
            'topic_key': topic_key or '',
            'topic': (topic_info or {}).get('title_it') or topic_input,
            'level': (topic_info or {}).get('level') or 'A2',
            'rule_en': (topic_info or {}).get('prompt_hint') or '',
        }
        text = generate_dictogloss_text(
            topic,
            str(api_keys.get('gemini') or os.getenv('GEMINI_API_KEY') or ''),
        )
        if text.get('error'):
            return jsonify(text), 400
        try:
            audio = generate_audio(
                text['text_it'],
                LANGUAGE_CONFIGS['Italian']['voice'],
                LANGUAGE_CONFIGS['Italian']['code'],
                str(api_keys.get('aws_access') or os.getenv('AWS_ACCESS_KEY') or ''),
                str(api_keys.get('aws_secret') or os.getenv('AWS_SECRET_KEY') or ''),
                engine=LANGUAGE_CONFIGS['Italian'].get('engine'),
            )
        except Exception as error:
            return jsonify({'error': f'Audio failed: {format_polly_error(error)}'}), 400
        session_id = create_dictogloss_session(topic, text)
        return jsonify({
            'session_id': session_id,
            'audio_b64': base64.b64encode(audio).decode(),
            'grammar_focus_en': text.get('grammar_focus_en') or '',
            'level': topic['level'],
            'word_count': len([w for w in text['text_it'].split() if w]),
        }), 200
    except Exception as error:
        return jsonify({'error': str(error)}), 400


@app.route('/api/grammar/dictogloss/check', methods=['POST'])
def grammar_dictogloss_check():
    try:
        data = request.json or {}
        session_id = str(data.get('sessionId') or '')
        session = dictogloss_session(session_id)
        if not session:
            return jsonify({'error': 'This dictogloss session has expired. Start a new text.'}), 400
        response_text = str(data.get('response') or '')
        feedback = generate_dictogloss_feedback(
            session['text_it'],
            response_text,
            session['topic'],
            str(
                (data.get('apiKeys') or {}).get('gemini')
                or os.getenv('GEMINI_API_KEY')
                or ''
            ),
        )
        if feedback.get('error'):
            return jsonify(feedback), 400
        result = record_dictogloss_result(
            PROJECT_DIR, session_id, response_text, feedback
        )
        payload = {
            key: value for key, value in feedback.items()
            if not key.startswith('_')
        }
        payload.update({
            key: value for key, value in result.items()
            if key != 'feedback'
        })
        return jsonify(payload), 200
    except Exception as error:
        return jsonify({'error': str(error)}), 400


@app.route('/api/insights/errors', methods=['GET'])
def insights_errors():
    """Merged recurring-error view across grammar, speaking, and word practice."""
    try:
        return jsonify(collect_errors(PROJECT_DIR)), 200
    except Exception as error:
        return jsonify({'error': str(error)}), 400

@app.route('/api/grammar/add', methods=['POST'])
def grammar_add():
    """Save generated atomic grammar cards to Anki across all modes."""
    data = request.json or {}
    card_data = data.get('data', {})
    audios_b64 = data.get('audios', {})

    cards = card_data.get('cards') or []
    if not cards:
        return jsonify({"error": "No cards data provided"}), 400

    try:
        ensure_grammar_model_and_deck()
    except Exception as error:
        return jsonify({"error": f"Could not set up Anki: {error}"}), 500

    mode = card_data.get('mode') or 'standard'
    topic_name = str(card_data.get('topic') or 'Grammar').strip()
    level = str(card_data.get('level') or 'A1').strip()
    topic_slug = re.sub(r'[^a-z0-9]+', '_', topic_name.lower()).strip('_')

    # Store audio files in Anki media
    card_audio_map = {}
    suffixes = GRAMMAR_AUDIO_SUFFIXES.get(mode, GRAMMAR_AUDIO_DEFAULT)
    for idx in range(1, len(cards) + 1):
        card_filenames = []
        for data_suffix, name_suffix in suffixes:
            audio_key = f"_card{idx}_{data_suffix}"
            if audio_key not in audios_b64:
                continue
            filename = f"grammar_{topic_slug}_c{idx}_{name_suffix}.mp3"
            try:
                invoke_anki("storeMediaFile", {
                    "filename": filename,
                    "data": audios_b64[audio_key],
                })
                card_filenames.append(filename)
            except Exception:
                pass
        card_audio_map[idx] = " ".join(f"[sound:{f}]" for f in card_filenames)

    # Insert notes
    added_count = 0
    skipped_count = 0
    errors = []

    for idx, card in enumerate(cards, start=1):
        if mode == "contrast":
            label = card.get('pair_label') or f"Pair {idx}"
            card_topic = f"{topic_name} — {label}"
        elif mode == "mistake":
            corr = card.get('corrected_element') or f"Mistake #{idx}"
            card_topic = f"{topic_name} — {corr}"
        else:
            target = str(card.get('target_form') or '').strip()
            card_topic = f"{topic_name} — {target}"

        front_html = str(card.get('front_html') or '').strip()
        back_html = str(card.get('back_html') or '').strip()
        audio_field = card_audio_map.get(idx, "")
        try:
            metadata_fields = anki_metadata_fields(card, card_data, idx)
        except ValueError as error:
            errors.append(f"Card {idx}: {error}")
            continue

        try:
            invoke_anki("addNote", {
                "note": {
                    "deckName": GRAMMAR_DECK_NAME,
                    "modelName": GRAMMAR_NOTE_TYPE,
                    "fields": {
                        "Topic": card_topic,
                        "Front": front_html,
                        "Back": back_html,
                        "Audio": audio_field,
                        "Level": level,
                        **metadata_fields,
                    },
                    "tags": [
                        "ag-grammar",
                        f"ag-grammar-{mode}",
                        *(
                            [f"ag-grammar-topic-{card_data.get('_topic_key')}"]
                            if card_data.get('_topic_key') else []
                        ),
                    ],
                    "options": {
                        "allowDuplicate": False,
                        "duplicateScope": "deck",
                        "duplicateScopeOptions": {
                            "deckName": GRAMMAR_DECK_NAME,
                            "checkChildren": True,
                        },
                    },
                },
            })
            added_count += 1
        except Exception as error:
            err_str = str(error).lower()
            if "duplicate" in err_str:
                skipped_count += 1
            else:
                errors.append(f"Card {idx}: {error}")

    if added_count == 0 and skipped_count > 0:
        return jsonify({
            "success": True,
            "topic": topic_name,
            "count": 0,
            "skipped": skipped_count,
            "message": f"All {skipped_count} cards for '{topic_name}' already exist in Anki.",
        }), 200

    if added_count == 0 and errors:
        return jsonify({"error": "; ".join(errors)}), 500

    return jsonify({
        "success": True,
        "topic": topic_name,
        "count": added_count,
        "skipped": skipped_count,
        "mode": mode,
    }), 200

if __name__ == '__main__':
    app.run(
        debug=True,
        port=int(os.getenv('ANKI_GENERATOR_PORT', '5001')),
    )
