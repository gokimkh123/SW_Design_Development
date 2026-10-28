# 기능: 공식 설문 파일을 우선 읽고 12문항의 구조와 선택값을 검증한다.
# 시스템 범위: 설문 API와 연결되며 공식 파일이 없을 때만 백엔드 초안을 읽는다.
# 결과: 검증된 설문을 반환하고 파일 손상이나 계약 불일치는 서버 오류로 전달한다.
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1)]
Time = Annotated[str, Field(pattern=r'^(?:[01][0-9]|2[0-3]):[0-5][0-9]$')]

# 프론트엔드 mock 및 API 계약의 선택값 순서. 문구는 JSON에서만 관리한다.
CHOICES = [
    ['insensitive', 'normal', 'sensitive', 'very_sensitive'],
    ['same', 'earlier', 'later', 'all_nighter'],
    ['daily', 'every_2_3_days', 'weekly', 'when_needed'],
    ['right_away', 'same_day', 'batch', 'when_piled'],
    ['warm', 'moderate', 'cool', 'any'],
    ['quietly_separate', 'when_needed', 'sometimes', 'often'],
    ['all_separate', 'supplies_only', 'ask_first', 'share_freely'],
    ['say_now', 'earplugs', 'talk_tomorrow', 'step_out'],
    ['ask_now', 'let_go', 'wait_and_talk', 'label_food'],
    ['say_now', 'do_it', 'talk_next_time', 'leave_note'],
    ['say_now', 'let_stay', 'after_friend_leaves', 'step_out'],
]


class SurveyModel(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')


class TimeField(SurveyModel):
    key: Literal['bedtime', 'wake']
    label: Text
    min: Time
    max: Time
    step_minutes: Literal[30]
    default: Time


class Option(SurveyModel):
    value: Text
    label: Text
    style: Literal['direct', 'avoid', 'delay'] | None = None


class Question(SurveyModel):
    question_id: str
    section: Literal['life', 'situation']
    type: Literal['time_range', 'choice']
    title: Text
    hint: Text | None = None
    fields: list[TimeField] | None = None
    options: list[Option] | None = None


class Survey(SurveyModel):
    version: Text
    questions: list[Question] = Field(min_length=12, max_length=12)

    @model_validator(mode='after')
    def check_contract(self):
        for index, question in enumerate(self.questions, 1):
            if question.question_id != f'q{index:02d}' or question.section != ('life' if index <= 8 else 'situation'):
                raise ValueError('문항 순서 또는 영역 오류')
            if index == 1:
                if question.type != 'time_range' or question.options is not None or not question.fields:
                    raise ValueError('시간 문항 형식 오류')
                fields = question.fields
                if [(f.key, f.min, f.max, f.step_minutes) for f in fields] != [
                    ('bedtime', '21:00', '03:00', 30), ('wake', '05:00', '11:00', 30)
                ]:
                    raise ValueError('시간 범위 오류')
                for field in fields:
                    minutes = lambda t: int(t[:2]) * 60 + int(t[3:])
                    offset = (minutes(field.default) - minutes(field.min)) % 1440
                    if offset > (minutes(field.max) - minutes(field.min)) % 1440 or offset % 30:
                        raise ValueError('기본 시각 오류')
            else:
                if question.type != 'choice' or question.fields is not None or not question.options:
                    raise ValueError('선택 문항 형식 오류')
                if [o.value for o in question.options] != CHOICES[index - 2]:
                    raise ValueError('선택값 또는 순서 오류')
                styles = ['direct', 'avoid', 'delay', 'delay' if index == 11 else 'avoid'] if index >= 9 else [None] * 4
                if [o.style for o in question.options] != styles:
                    raise ValueError('대화 방식 오류')
        return self


def load_survey(official: Path, draft: Path) -> Survey:
    try:
        content = official.read_text(encoding='utf-8')
    except FileNotFoundError:
        # 끊어진 심볼릭 링크 역시 공식 파일 손상으로 처리한다.
        if official.is_symlink():
            raise
        content = draft.read_text(encoding='utf-8')
        result = Survey.model_validate(json.loads(content))
        if not result.version.startswith('provisional-'):
            raise ValueError('초안 버전 표시 누락')
        return result
    return Survey.model_validate(json.loads(content))
