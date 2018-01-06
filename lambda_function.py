# coding:utf-8
import logging
import os
import traceback
import time
import requests
import json
from datetime import datetime, timedelta

error_slack_url = os.environ.get('ERROR_SLACK_URL', None)
error_slack_channel = os.environ.get('ERROR_SLACK_CHANNEL', None)
log_level = os.environ.get('LOG_LEVEL', 'ERROR')
logger = logging.getLogger()


# --------------- Log level set ----------------------
def logger_level(level):
    if level == 'CRITICAL':
        return 50
    elif level == 'ERROR':
        return 40
    elif level == 'WARNING':
        return 30
    elif level == 'INFO':
        return 20
    elif level == 'DEBUG':
        return 10
    else:
        return 0


logger.setLevel(logger_level(log_level))


# --------------- Helpers that build all of the responses ----------------------

def build_speechlet_response(title, output, reprompt_text, should_end_session):
    return {
        'outputSpeech': {
            'type': 'PlainText',
            'text': output
        },
        'card': {
            'type': 'Simple',
            'title': "SessionSpeechlet - " + title,
            'content': "SessionSpeechlet - " + output[0:8000]
        },
        'reprompt': {
            'outputSpeech': {
                'type': 'PlainText',
                'text': reprompt_text[0:8000]
            }
        },
        'shouldEndSession': should_end_session
    }


def build_response(session_attributes, speechlet_response):
    return {
        'version': '1.0',
        'sessionAttributes': session_attributes,
        'response': speechlet_response
    }


# --------------- Functions that control the skill's behavior ------------------

def get_welcome_response():
    session_attributes = {}
    card_title = "Welcome"
    speech_output = u'何のフィードをチェックしますか'
    reprompt_text = u'何のフィードをチェックしますか'
    should_end_session = False
    return build_response(session_attributes, build_speechlet_response(
        card_title, speech_output, reprompt_text, should_end_session))


def handle_session_end_request():
    session_attributes = {}
    card_title = "Session Ended"
    speech_output = u'フィードチェックを終了します'
    reprompt_text = u'フィードチェックを終了します'
    should_end_session = True
    return build_response(session_attributes, build_speechlet_response(
        card_title, speech_output, reprompt_text, should_end_session))


def create_feed_attributes(feed):
    return {"feed": feed}


def get_feed(feedly_tag):
    feedly_userid = os.environ.get('FEEDLY_ID', None)
    feedly_token = os.environ.get('FEEDLY_TOKEN', None)
    interval_days = int(os.environ.get('INTERVAL_MINUTE', '1'))
    feed_count = int(os.environ.get('FEED_COUNT', '10'))

    interval_time = datetime.now() - timedelta(days=interval_days)

    unix_time = int(time.mktime(interval_time.timetuple())) * 1000
    logger.debug(unix_time)

    headers = {'Authorization': feedly_token}
    response_stream = requests.get(
        '{url}{user}/tag/{tag}&count={count}&newerThan={time}'.format(
            url='https://cloud.feedly.com/v3/streams/contents?streamId=user/',
            user=feedly_userid,
            tag=feedly_tag,
            count=feed_count,
            time=unix_time
        ),
        headers=headers
    )
    stream_data = json.loads(response_stream.text)
    logger.debug(stream_data)

    if not ('items' in stream_data):
        return None

    stream_datas = stream_data['items']
    return stream_datas


def get_feed_speech(intent, session, feedly_tag):
    card_title = intent['name']
    session_attributes = create_feed_attributes('other')
    should_end_session = True

    stream_datas = get_feed(feedly_tag)

    if stream_datas is None or len(stream_datas) == 0:
        return handle_session_end_request()

    card_title = "Speech Feed"

    speechs = []
    for stream in stream_datas:
        speechs.append(stream['title'])

    speech_output = ','.join(speechs)
    reprompt_text = ','.join(speechs)

    return build_response(session_attributes, build_speechlet_response(
        card_title, speech_output, reprompt_text, should_end_session))


# --------------- Events ------------------

def on_session_started(session_started_request, session):
    logger.info("on_session_started requestId=" + session_started_request['requestId'] +
                ", sessionId=" + session['sessionId'])


def on_launch(launch_request, session):
    logger.info("on_launch requestId=" + launch_request['requestId'] +
                ", sessionId=" + session['sessionId'])
    return get_welcome_response()


def on_intent(intent_request, session):
    logger.info("on_intent requestId=" + intent_request['requestId'] +
                ", sessionId=" + session['sessionId'])

    intent = intent_request['intent']
    intent_name = intent_request['intent']['name']

    if intent_name == "OtherNewsIntent":
        return get_feed_speech(intent, session, '0mail')
    elif intent_name == "AWSNewsIntent":
        return get_feed_speech(intent, session, 'aws')
    elif intent_name == "AMAZON.HelpIntent":
        return get_welcome_response()
    elif intent_name == "AMAZON.CancelIntent" or intent_name == "AMAZON.StopIntent":
        return handle_session_end_request()
    else:
        raise ValueError("Invalid intent")


def on_session_ended(session_ended_request, session):
    logger.info("on_session_ended requestId=" + session_ended_request['requestId'] +
                ", sessionId=" + session['sessionId'])
    return handle_session_end_request()


# --------------- Main handler ------------------

def lambda_handler(event, context):
    try:
        logger.debug(event)
        logger.info("event.session.application.applicationId=" +
          event['session']['application']['applicationId'])

        if event['session']['new']:
            on_session_started({'requestId': event['request']['requestId']},
                               event['session'])

        if event['request']['type'] == "LaunchRequest":
            return on_launch(event['request'], event['session'])
        elif event['request']['type'] == "IntentRequest":
            return on_intent(event['request'], event['session'])
        elif event['request']['type'] == "SessionEndedRequest":
            return on_session_ended(event['request'], event['session'])

    except:
        logger.error(traceback.format_exc())
        requests.post(
            error_slack_url,
            json.dumps(
                {
                    'text': 'alexa_feed error\n{message}'.format(
                        message=traceback.format_exc()
                    ),
                    'channel': error_slack_channel
                }
            )
        )
        raise Exception(traceback.format_exc())
