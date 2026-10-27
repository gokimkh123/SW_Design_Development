import type { Answers, SurveyQuestion } from '../api/types';

/** Validates against the survey returned by the API, never against local copy. */
export function isAnswerComplete(question: SurveyQuestion, answer: Answers[string] | undefined): boolean {
  if (question.type === 'choice') {
    return typeof answer === 'string' && (question.options ?? []).some((option) => option.value === answer);
  }
  if (!answer || typeof answer === 'string') return false;
  return (question.fields ?? []).length > 0 && (question.fields ?? []).every((field) => {
    const value = answer[field.key];
    if (typeof value !== 'string' || !/^\d{2}:\d{2}$/.test(value)) return false;
    const minutes = (time: string) => Number(time.slice(0, 2)) * 60 + Number(time.slice(3));
    const start = minutes(field.min);
    const end = minutes(field.max) + (minutes(field.max) < start ? 1440 : 0);
    let selected = minutes(value);
    if (selected < start) selected += 1440;
    return selected >= start && selected <= end && (selected - start) % field.step_minutes === 0;
  });
}

export function areAnswersComplete(questions: SurveyQuestion[], answers: Answers): boolean {
  return questions.length === 12 &&
    questions.filter((q) => q.section === 'life').length === 8 &&
    questions.filter((q) => q.section === 'situation').length === 4 &&
    questions.every((question) => isAnswerComplete(question, answers[question.question_id]));
}
