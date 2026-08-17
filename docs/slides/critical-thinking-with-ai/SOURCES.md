# Critical thinking × AI — slide deck

Three slides for a healthcare IT audience on using AI with critical thinking:
which tool, which sources, what to fact-check.

- `critical-thinking-with-ai.pptx` — the deck (speaker notes included on every slide)
- `critical-thinking-with-ai.pdf` — handout/preview version
- `slide-1.jpg` … `slide-3.jpg` — rendered previews
- `generate_deck.js` — regenerates the deck (`node generate_deck.js`, needs
  `pptxgenjs`, `react`, `react-dom`, `react-icons`, `sharp` on `NODE_PATH`)

**Before presenting:** slide 2 says "our internal AI" — swap in the actual tool
name. Edit `generate_deck.js` and re-run, or edit the text box directly in
PowerPoint.

## Sources behind every factual claim

Nothing on these slides is invented. Each claim traces to a public, checkable
source (all also cited in the slide 3 speaker notes):

1. **"319 knowledge workers studied — Microsoft Research + Carnegie Mellon, 2025"
   and the trust/critical-thinking finding.**
   Lee, Hao-Ping (Hank), et al., *The Impact of Generative AI on Critical
   Thinking: Self-Reported Reductions in Cognitive Effort and Confidence Effects
   From a Survey of Knowledge Workers*, CHI 2025. Survey of 319 knowledge
   workers covering 936 real AI-use examples: higher confidence in the AI was
   associated with less critical thinking; higher self-confidence with more.
   <https://www.microsoft.com/en-us/research/publication/the-impact-of-generative-ai-on-critical-thinking-self-reported-reductions-in-cognitive-effort-and-confidence-effects-from-a-survey-of-knowledge-workers/>

2. **"Air Canada, 2024 — a tribunal held the airline liable after its website
   chatbot invented a bereavement-refund policy."**
   *Moffatt v. Air Canada*, British Columbia Civil Resolution Tribunal,
   February 2024. The tribunal rejected the argument that the chatbot was "a
   separate legal entity" and awarded ~CA$812.
   <https://www.mccarthy.ca/en/insights/blogs/techlex/moffatt-v-air-canada-misrepresentation-ai-chatbot>

3. **"AP investigation, 2024 — an AI transcription tool used by 30,000+
   clinicians invented text no one said."**
   Associated Press investigation, October 26, 2024, on hallucinations in
   OpenAI's Whisper speech-to-text and a Whisper-based medical transcription
   tool (Nabla) used by 30,000+ clinicians across ~40 health systems. OpenAI
   itself advises against use in high-risk decision contexts. Coverage:
   <https://fortune.com/2024/10/26/openai-transcription-tool-whisper-hallucination-rate-ai-tools-hospitals-patients-doctors>,
   <https://www.healthcareitnews.com/news/openais-general-purpose-speech-recognition-model-flawed-researchers-say>

4. **"Acting on wrong automated output ('automation bias') is a documented risk
   in clinical software."**
   Goddard, Roudsari & Wyatt, *Automation bias: a systematic review of
   frequency, effect mediators, and mitigators*, JAMIA 19(1):121–127, 2012.
   <https://academic.oup.com/jamia/article-abstract/19/1/121/732254>
