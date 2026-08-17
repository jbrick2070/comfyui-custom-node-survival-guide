// Generates critical-thinking-with-ai.pptx — 3 slides for a healthcare IT audience.
// Run: node generate_deck.js   (from this directory)

const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const {
  FiCrosshair, FiDatabase, FiCheckCircle, FiBookOpen, FiFileText,
  FiMessageCircle, FiAlertTriangle, FiActivity,
} = require("react-icons/fi");

// ---------- palette (healthcare teal) ----------
const INK = "0B3C46";        // deep teal ink — dark backgrounds, headings on light
const CARD_DARK = "104A57";  // cards on dark slides
const TEAL = "0E7C8A";       // primary
const MINT = "02C39A";       // accent
const ICE = "CFE6E9";        // body text on dark
const WHITE = "FFFFFF";
const TINT_TEAL = "E8F3F4";  // card tint on light
const TINT_GRAY = "F1F4F5";
const AMBER = "E8A33D";      // caution accent
const BODY = "3E5A63";       // body text on light

const HEAD = "Cambria";
const SANS = "Calibri";

async function iconPng(Comp, hex) {
  let svg = ReactDOMServer.renderToStaticMarkup(
    React.createElement(Comp, { size: 512, strokeWidth: 2 })
  );
  svg = svg.replace(/currentColor/g, `#${hex}`);
  const buf = await sharp(Buffer.from(svg)).resize(256, 256).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

(async () => {
  const icons = {
    crosshair: await iconPng(FiCrosshair, INK),
    database: await iconPng(FiDatabase, INK),
    check: await iconPng(FiCheckCircle, INK),
    book: await iconPng(FiBookOpen, WHITE),
    file: await iconPng(FiFileText, WHITE),
    chat: await iconPng(FiMessageCircle, WHITE),
    alert: await iconPng(FiAlertTriangle, INK),
    activity: await iconPng(FiActivity, INK),
  };

  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
  pres.author = "Healthcare IT — internal";
  pres.title = "Critical thinking x AI";

  const iconCircle = (slide, x, y, dia, fill, iconData, iconScale = 0.55) => {
    slide.addShape("ellipse", { x, y, w: dia, h: dia, fill: { color: fill } });
    const s = dia * iconScale;
    const off = (dia - s) / 2;
    slide.addImage({ data: iconData, x: x + off, y: y + off, w: s, h: s });
  };

  // ============================== SLIDE 1 ==============================
  {
    const s = pres.addSlide();
    s.background = { color: INK };

    s.addText("AI AT WORK  ·  HEALTHCARE IT", {
      x: 0.72, y: 0.5, w: 9, h: 0.3, margin: 0,
      fontFace: SANS, fontSize: 12, bold: true, color: MINT, charSpacing: 3,
    });
    s.addText("Think first, then prompt", {
      x: 0.7, y: 0.86, w: 11.9, h: 0.78, margin: 0,
      fontFace: HEAD, fontSize: 40, bold: true, color: WHITE,
    });
    s.addText(
      "Critical thinking is what makes AI useful — and safe — in our work. Three questions before every AI task:",
      { x: 0.72, y: 1.74, w: 11.9, h: 0.4, margin: 0, fontFace: SANS, fontSize: 15, color: ICE }
    );

    const cards = [
      {
        n: "01", icon: icons.crosshair, q: "What am I actually asking?",
        body: "Name the task before you type. Compare two lists. Find the exceptions. Summarize a policy. Draft a first version. A sharper ask gets a sharper answer.",
      },
      {
        n: "02", icon: icons.database, q: "What sources does it need?",
        body: "Don’t assume the AI “just knows.” Point it at the right material first — our documentation, the spec, the policy. No sources, no trust.",
      },
      {
        n: "03", icon: icons.check, q: "What will I fact-check?",
        body: "Decide before you read the answer, not after. Names, numbers, versions, claims about functionality — verify anything you’ll act on.",
      },
    ];
    cards.forEach((c, i) => {
      const x = 0.7 + i * 4.08; // w 3.78 + gap 0.3
      s.addShape("roundRect", {
        x, y: 2.42, w: 3.78, h: 4.28, rectRadius: 0.1, fill: { color: CARD_DARK },
      });
      iconCircle(s, x + 0.32, 2.78, 0.68, MINT, c.icon);
      s.addText(c.n, {
        x: x + 3.78 - 0.85, y: 2.84, w: 0.55, h: 0.4, margin: 0, align: "right",
        fontFace: HEAD, fontSize: 15, bold: true, color: MINT,
      });
      s.addText(c.q, {
        x: x + 0.32, y: 3.78, w: 3.14, h: 0.78, margin: 0, valign: "top",
        fontFace: SANS, fontSize: 17.5, bold: true, color: WHITE,
      });
      s.addText(c.body, {
        x: x + 0.32, y: 4.6, w: 3.14, h: 1.9, margin: 0, valign: "top",
        fontFace: SANS, fontSize: 13, color: ICE, lineSpacingMultiple: 1.18,
      });
    });

    s.addNotes(
      "Framing: we are not anti-AI — we use it every day. The skill is thinking before and after the prompt.\n" +
      "Tip: ask the room for one AI task from their week and run it through the three questions live.\n" +
      "Q1 gives the task a shape (compare / find exceptions / summarize / draft). Q2 is grounding — the AI only knows what it can see. Q3 sets the verification bar BEFORE reading the answer, which is when we are least biased."
    );
  }

  // ============================== SLIDE 2 ==============================
  {
    const s = pres.addSlide();
    s.background = { color: WHITE };

    s.addText("RECIPES THAT WORK", {
      x: 0.72, y: 0.5, w: 9, h: 0.3, margin: 0,
      fontFace: SANS, fontSize: 12, bold: true, color: TEAL, charSpacing: 3,
    });
    s.addText("Match the tool to the task — then feed it sources", {
      x: 0.7, y: 0.84, w: 11.9, h: 0.62, margin: 0,
      fontFace: HEAD, fontSize: 30, bold: true, color: INK,
    });

    // ---- Card A: internal AI + grounding recipe
    s.addShape("roundRect", {
      x: 0.7, y: 1.66, w: 6.35, h: 3.78, rectRadius: 0.1, fill: { color: TINT_TEAL },
    });
    iconCircle(s, 1.0, 1.96, 0.6, TEAL, icons.book);
    s.addText("Questions about documentation, features & functionality", {
      x: 1.78, y: 1.9, w: 5.05, h: 0.72, margin: 0, valign: "middle",
      fontFace: SANS, fontSize: 15.5, bold: true, color: INK,
    });
    s.addText([
      { text: "→  Use our internal AI", options: { bold: true, color: TEAL } },
      { text: " — it searches our document sources.", options: { color: BODY } },
    ], {
      x: 1.0, y: 2.76, w: 5.75, h: 0.34, margin: 0, fontFace: SANS, fontSize: 13,
    });
    s.addText("THE GROUNDING RECIPE", {
      x: 1.0, y: 3.18, w: 4, h: 0.28, margin: 0,
      fontFace: SANS, fontSize: 10.5, bold: true, color: TEAL, charSpacing: 2,
    });
    const steps = [
      "Point it at the right document sources for your topic.",
      "First: “Write a short report on what our docs say about X.”",
      "Then ask your real question against that report.",
      "Ask for quotes + doc names so you can spot-check fast.",
    ];
    steps.forEach((t, i) => {
      const y = 3.56 + i * 0.46;
      s.addShape("ellipse", { x: 1.0, y, w: 0.3, h: 0.3, fill: { color: TEAL } });
      s.addText(String(i + 1), {
        x: 1.0, y, w: 0.3, h: 0.3, margin: 0, align: "center", valign: "middle",
        fontFace: SANS, fontSize: 11.5, bold: true, color: WHITE,
      });
      s.addText(t, {
        x: 1.46, y: y - 0.04, w: 5.35, h: 0.38, margin: 0, valign: "middle",
        fontFace: SANS, fontSize: 12.5, color: BODY,
      });
    });

    // ---- Card B: Copilot for documents
    s.addShape("roundRect", {
      x: 7.35, y: 1.66, w: 5.28, h: 1.78, rectRadius: 0.1, fill: { color: TINT_GRAY },
    });
    iconCircle(s, 7.65, 1.94, 0.6, INK, icons.file);
    s.addText("Creating documents & deliverables", {
      x: 8.43, y: 1.9, w: 4.0, h: 0.68, margin: 0, valign: "middle",
      fontFace: SANS, fontSize: 15.5, bold: true, color: INK,
    });
    s.addText([
      { text: "→  Use Copilot for Word, Excel & Outlook", options: { bold: true, color: TEAL, breakLine: true } },
      { text: "It works inside the file. Hand it the source material; review every name and number it writes.", options: { color: BODY } },
    ], {
      x: 7.65, y: 2.62, w: 4.68, h: 0.74, margin: 0, fontFace: SANS, fontSize: 12.5,
      lineSpacingMultiple: 1.1,
    });

    // ---- Card C: everything else
    s.addShape("roundRect", {
      x: 7.35, y: 3.66, w: 5.28, h: 1.78, rectRadius: 0.1, fill: { color: TINT_GRAY },
    });
    iconCircle(s, 7.65, 3.94, 0.6, TEAL, icons.chat);
    s.addText("Drafting, brainstorming, rewriting", {
      x: 8.43, y: 3.9, w: 4.0, h: 0.68, margin: 0, valign: "middle",
      fontFace: SANS, fontSize: 15.5, bold: true, color: INK,
    });
    s.addText([
      { text: "→  Any assistant works — the recipe is your judgment.", options: { bold: true, color: TEAL, breakLine: true } },
      { text: "The three questions always run first: task, sources, fact-check.", options: { color: BODY } },
    ], {
      x: 7.65, y: 4.62, w: 4.68, h: 0.74, margin: 0, fontFace: SANS, fontSize: 12.5,
      lineSpacingMultiple: 1.1,
    });

    // ---- bottom strip: prompts that make it think
    s.addShape("roundRect", {
      x: 0.7, y: 5.72, w: 11.93, h: 1.28, rectRadius: 0.1, fill: { color: INK },
    });
    s.addText("PROMPTS THAT MAKE IT THINK", {
      x: 1.05, y: 5.9, w: 5, h: 0.28, margin: 0,
      fontFace: SANS, fontSize: 10.5, bold: true, color: MINT, charSpacing: 2,
    });
    const quotes = [
      "“Compare these lists — what changed?”",
      "“List the exceptions and edge cases.”",
      "“What would make this answer wrong?”",
    ];
    quotes.forEach((q, i) => {
      s.addText(q, {
        x: 1.05 + i * 3.81, y: 6.26, w: 3.61, h: 0.56, margin: 0, valign: "top",
        fontFace: SANS, fontSize: 12.5, italic: true, color: WHITE,
      });
    });

    s.addNotes(
      "Before presenting: swap “our internal AI” for the actual tool name.\n" +
      "Why report-first (step 2): making the AI show what the documents say BEFORE answering keeps it anchored to real sources and exposes gaps — if the report is thin, you know the docs don’t cover it, and the answer that follows deserves extra scrutiny. Asking for quotes and doc names (step 4) turns fact-checking from a chore into a 30-second spot-check.\n" +
      "Grounded answers still get spot-checked: retrieval reduces errors, it does not eliminate them.\n" +
      "Copilot: best when the deliverable is the file itself (Word/Excel/Outlook) — it keeps formatting and works on the actual document. Same critical-thinking rules apply."
    );
  }

  // ============================== SLIDE 3 ==============================
  {
    const s = pres.addSlide();
    s.background = { color: INK };

    s.addText("WHY IT MATTERS  ·  DOCUMENTED CASES, NOT VIBES", {
      x: 0.72, y: 0.5, w: 10, h: 0.3, margin: 0,
      fontFace: SANS, fontSize: 12, bold: true, color: MINT, charSpacing: 3,
    });
    s.addText("Trust, but verify", {
      x: 0.7, y: 0.84, w: 11.9, h: 0.62, margin: 0,
      fontFace: HEAD, fontSize: 30, bold: true, color: WHITE,
    });

    // ---- left: the study
    s.addShape("roundRect", {
      x: 0.7, y: 1.68, w: 4.9, h: 4.02, rectRadius: 0.1, fill: { color: CARD_DARK },
    });
    s.addText("319", {
      x: 1.0, y: 1.92, w: 4.3, h: 0.95, margin: 0,
      fontFace: HEAD, fontSize: 60, bold: true, color: MINT,
    });
    s.addText([
      { text: "knowledge workers studied", options: { bold: true, color: WHITE, breakLine: true } },
      { text: "Microsoft Research + Carnegie Mellon, 2025", options: { color: ICE, fontSize: 11.5 } },
    ], {
      x: 1.0, y: 2.98, w: 4.3, h: 0.62, margin: 0, fontFace: SANS, fontSize: 13,
    });
    s.addText(
      "The more people trusted the AI, the less critical thinking they reported. Confidence in their own expertise went the other way — more checking, sharper results.",
      {
        x: 1.0, y: 3.78, w: 4.3, h: 1.7, margin: 0, valign: "top",
        fontFace: SANS, fontSize: 13.5, color: ICE, lineSpacingMultiple: 1.2,
      }
    );

    // ---- right rows
    const rows = [
      {
        y: 1.68, icon: icons.alert, circle: AMBER,
        head: "The chatbot’s answer is your answer",
        body: "Air Canada, 2024 — a tribunal held the airline liable after its website chatbot invented a bereavement-refund policy that didn’t exist. “The AI said it” was no defense.",
      },
      {
        y: 3.84, icon: icons.activity, circle: MINT,
        head: "In healthcare, the stakes are higher",
        body: "AP investigation, 2024 — an AI transcription tool used by 30,000+ clinicians invented text no one said. Acting on wrong automated output (“automation bias”) is a documented risk in clinical software.",
      },
    ];
    rows.forEach((r) => {
      s.addShape("roundRect", {
        x: 5.9, y: r.y, w: 6.73, h: 1.86, rectRadius: 0.1, fill: { color: CARD_DARK },
      });
      iconCircle(s, 6.2, r.y + 0.28, 0.6, r.circle, r.icon);
      s.addText(r.head, {
        x: 6.98, y: r.y + 0.24, w: 5.45, h: 0.66, margin: 0, valign: "middle",
        fontFace: SANS, fontSize: 15, bold: true, color: WHITE,
      });
      s.addText(r.body, {
        x: 6.2, y: r.y + 0.94, w: 6.13, h: 0.86, margin: 0, valign: "top",
        fontFace: SANS, fontSize: 12, color: ICE, lineSpacingMultiple: 1.12,
      });
    });

    // ---- closing band
    s.addShape("roundRect", {
      x: 0.7, y: 5.98, w: 11.93, h: 0.95, rectRadius: 0.1, fill: { color: MINT },
    });
    s.addText([
      { text: "AI drafts. You decide.  ", options: { bold: true, fontSize: 16 } },
      { text: "Verify anything that leaves the building — names, numbers, dates, functionality claims.", options: { fontSize: 13 } },
    ], {
      x: 1.05, y: 5.98, w: 11.3, h: 0.95, margin: 0, valign: "middle",
      fontFace: SANS, color: INK,
    });

    s.addNotes(
      "Sources (all public, checkable):\n" +
      "1) Lee, Hao-Ping (Hank) et al., “The Impact of Generative AI on Critical Thinking: Self-Reported Reductions in Cognitive Effort and Confidence Effects From a Survey of Knowledge Workers,” CHI 2025 (Microsoft Research + Carnegie Mellon). 319 knowledge workers, 936 real AI-use examples. Higher confidence in the AI correlated with LESS critical thinking; higher self-confidence with MORE. https://www.microsoft.com/en-us/research/publication/the-impact-of-generative-ai-on-critical-thinking-self-reported-reductions-in-cognitive-effort-and-confidence-effects-from-a-survey-of-knowledge-workers/\n" +
      "2) Moffatt v. Air Canada, British Columbia Civil Resolution Tribunal, Feb 2024. Chatbot invented a retroactive bereavement-fare refund; tribunal rejected Air Canada’s claim that the chatbot was “a separate legal entity” and awarded ~CA$812. https://www.mccarthy.ca/en/insights/blogs/techlex/moffatt-v-air-canada-misrepresentation-ai-chatbot\n" +
      "3) Associated Press investigation, Oct 26, 2024: OpenAI’s Whisper speech-to-text hallucinating fabricated sentences; a Whisper-based medical tool (Nabla) used by 30,000+ clinicians across ~40 health systems. OpenAI itself advises against use in high-risk decision contexts. Coverage: https://fortune.com/2024/10/26/openai-transcription-tool-whisper-hallucination-rate-ai-tools-hospitals-patients-doctors and https://www.healthcareitnews.com/news/openais-general-purpose-speech-recognition-model-flawed-researchers-say\n" +
      "4) Goddard, Roudsari & Wyatt, “Automation bias: a systematic review of frequency, effect mediators, and mitigators,” JAMIA 19(1):121–127, 2012 — automation bias is a robust, measurable effect in clinical decision support. https://academic.oup.com/jamia/article-abstract/19/1/121/732254\n" +
      "Delivery tip: end on the band — “AI drafts. You decide.” is the one line to remember."
    );
  }

  await pres.writeFile({ fileName: "critical-thinking-with-ai.pptx" });
  console.log("Wrote critical-thinking-with-ai.pptx");
})();
