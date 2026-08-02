/**
 * Three questions to open the conversation with, chosen from what this run actually found.
 *
 * A blank composer is the reason most demo chatbots never get used: a judge with thirty seconds
 * does not invent a question about late blight. These are the questions the corpus can answer
 * well, which is not a trick — the whole point of the Advisor is that it refuses outside its
 * ten documents, so the opening move should be inside them.
 *
 * Pure, no React, so it can be asserted from Node.
 */

// Asked of every run that produced a plan. Ordered by what a farmer standing in the field wants
// first: what to do now, then the thing most likely to waste the spray, then the follow-up.
const TREATMENT = [
  'Why do I need to remove the infected leaves first?',
  'Can I spray before rain?',
  'Why re-inspect after seven days?',
]

// A run where nothing shipped. The first question is the one a judge will actually ask, and it
// is answered from the ruling rather than the corpus — see `withheld_answer` in agents/advisor.py.
const WITHHELD = [
  'Why was the advice withheld?',
  'What should I do now?',
  'How do I take a better photograph?',
]

// A clean field. There is no disease to ask about, so the useful questions are about not
// getting one.
const CLEAN = [
  'How often should I scan the field?',
  'What conditions cause an outbreak?',
  'How do I stop resistance building up?',
]

/**
 * @param {{blocked?: boolean, crossCheck?: string, disease?: string|null, hasPlan?: boolean}} run
 * @returns {string[]} exactly three questions
 */
export function suggestedQuestions({ blocked, crossCheck, disease, hasPlan } = {}) {
  if (blocked || crossCheck === 'contested') return WITHHELD
  if (!hasPlan || !disease) return CLEAN
  const named = String(disease).replaceAll('_', ' ')
  // One question names the diagnosis, so the suggestions visibly belong to *this* scan rather
  // than being three constants that would fit any field.
  return [`What does ${named} look like?`, ...TREATMENT.slice(0, 2)]
}
