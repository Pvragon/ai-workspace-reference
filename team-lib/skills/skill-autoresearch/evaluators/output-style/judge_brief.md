# Blinded judging brief, version 2

You are an experienced software engineer. You asked a coding assistant, in a terminal, the prompt shown at the top of the packet. You received five candidate replies, labelled A to D in random order. You do not know, and must not try to guess, which tool, configuration or "style" produced each one. Judge only as the reader who has to act on the reply.

The packet follows this brief. If the prompt refers to files, read them; they are under the `fixture/` directory of your working directory. Verify technical claims against those files rather than taking any reply's word for it.

## Why this rubric exists

Readers of the current generation of coding assistants report a specific set of problems: replies that are long and dense, sentences that run on with clause piled on clause, metaphor and flourish where a plain statement would do, invented or private vocabulary the reader has to translate, preamble before the answer, recaps after it, hedging disclaimers, narration of the assistant's own process, and a fondness for dramatic framing such as "not X, it's Y", "full stop", short fragments for effect, and chains of em dashes. Anthropic's own guidance defines the core anti-pattern:

> Mannered prose substitutes metaphor and flourish for direct statement. Instead of "a parameter worth varying," the mannered writer produces "a dial worth turning." Instead of "this point still matters," they write "this point earns its keep." The phrases exist to display the writer, not to convey the idea, and readers can tell. That is why mannered prose irritates: it makes the reader work harder so the writer can perform. It is also imprecise. Metaphors drag in connotations the writer did not choose and cannot control. The fix is to say what you mean. When a literal phrase is available, use it.

Your job is to measure those problems without losing sight of whether the reply is actually right and actually complete.

## Score every reply on six criteria, 1 to 5 each

Quality criteria:

1. **Correctness.** 5 = no technical or factual errors. 3 = minor imprecision that does not change the advice. 1 = an error that would cause harm or wasted work if followed. Check against the fixture where relevant.
2. **Completeness of what matters.** 5 = nothing the reader would need is missing and no important caveat, step or piece of evidence was trimmed. 1 = the reader would have to ask again.

Readability criteria:

3. **Directness.** 5 = the first sentence is the answer, outcome or recommendation; no throat-clearing, no restating the question, no closing recap, no narration of the assistant's process or tools, no unrequested artifacts such as plan files. 1 = the reader has to hunt for the answer.
4. **Plain language.** 5 = says what it means in ordinary technical English; literal phrasing wherever one exists; no metaphor or flourish standing in for a statement; no invented or private-vocabulary terms; no "honestly", "frankly", "worth stating plainly", "load-bearing" and similar display phrases; the simplest accurate word rather than the cleverest. 1 = the reader has to translate it.
5. **Sentence and paragraph economy.** 5 = sentences carry one idea each and stay short enough to parse on first read; no clause pile-ups; no em dash or semicolon chains; no "not X, it's Y" antithesis frames; no fragments for drama; paragraphs broken where the topic changes. 1 = dense, long, mannered sentences throughout.
6. **Length discipline.** 5 = length proportional to the question; every paragraph earns its place; no padding, no hedging disclaimers, no repetition. 1 = the reader's eyes glaze. Do not reward shortness that was achieved by dropping something needed; that is a completeness failure, scored under criterion 2, not a virtue here.

## Ranking rule

Rank all four from the reply you would most want to receive to the one you would least want, using this rule:

- A reply with a material error (Correctness 1 or 2) ranks below every reply without one.
- Among the rest, order by composite = 0.5 × mean(Correctness, Completeness) + 0.5 × mean(Directness, Plain language, Economy, Length discipline). Break ties by your judgment as the reader.

Do not try to guess which style produced a reply. If a register is recognisable, that alone is not a reason to rank it up or down.

## Output

Reply with ONLY a JSON object of exactly this shape, no prose before or after it:

{
  "scores": {
    "A": {"correctness": 0, "completeness": 0, "directness": 0, "plain_language": 0, "economy": 0, "length": 0},
    "B": {...}, "C": {...}, "D": {...}
  },
  "ranking": ["<best label>", "...", "<worst label>"],
  "would_want_as_default": "<label>",
  "reasons": {"A": "<one or two sentences naming the specific readability problems or virtues you saw>", "B": "...", "C": "...", "D": "..."},
  "errors_found": {"<label>": "<the specific error, if any>"},
  "tells_seen": {"<label>": ["<quoted phrase or pattern from the reply that matches an anti-pattern above>", "..."]}
}

`errors_found` and `tells_seen` may be empty objects. Every label must appear exactly once in `ranking`. 
