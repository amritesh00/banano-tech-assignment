const { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
        Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle } = require("docx");
const fs = require("fs");

const FONT = "Georgia";
const PAGE_W = 12240, PAGE_H = 15840; // US Letter

function p(text, opts={}) {
  return new Paragraph({
    spacing: { after: opts.after ?? 120, before: opts.before ?? 0 },
    children: [new TextRun({ text, font: FONT, size: opts.size ?? 21, bold: opts.bold, italics: opts.italics, color: opts.color })],
    alignment: opts.align,
  });
}
function rule() {
  return new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "C9C2B2" } },
    spacing: { after: 160 },
  });
}
function bullet(text, opts={}) {
  return new Paragraph({
    spacing: { after: 80 },
    indent: { left: 260 },
    bullet: { level: 0 },
    children: [new TextRun({ text, font: FONT, size: 21, bold: opts.bold })],
  });
}

const doc = new Document({
  sections: [{
    properties: { page: { size: { width: PAGE_W, height: PAGE_H }, margin: { top: 900, bottom: 900, left: 1080, right: 1080 } } },
    children: [
      new Paragraph({ spacing: { after: 20 }, children: [new TextRun({ text: "MEMO", font: FONT, size: 18, color: "8A7F63", bold: true })] }),
      new Paragraph({
        spacing: { after: 60 },
        children: [new TextRun({ text: "Who's actually driving CSAT down — and who the Q3 budget should skip", font: FONT, size: 30, bold: true })],
      }),
      new Paragraph({
        spacing: { after: 200 },
        children: [new TextRun({ text: "To Priya Raman, Head of Customer Experience  ·  Re: CSAT dashboard, bottom-10 flag, Q3 training spend", font: FONT, size: 19, italics: true, color: "5C5647" })],
      }),
      rule(),

      p("The short version", { bold: true, size: 22, after: 60 }),
      p("Ranking agents by raw CSAT — the obvious way to build this — would point the whole Rs 4,00,000 Q3 budget at the wrong ten people. Every one of the naive bottom 10 turns out to be on a structurally harder queue (deliveries, returns, warranty, or a hardware-triage line within Chat), not someone who needs coaching. The corrected bottom 10 in the dashboard is a different ten entirely — three Billing, three Email, two Voice, two Chat — and it's the list worth training against.", { after: 140 }),

      p("Why the raw ranking is wrong", { bold: true, size: 22, after: 60 }),
      bullet("Logistics, Returns Desk and Escalations & Warranty (10 agents) handle tickets that reach them after a customer has already waited days for a delivery, return, or repair. 24-hour-plus handling and lower CSAT are the nature of that queue, not the agent."),
      bullet("A four-person hardware-triage rota inside Chat — Kapoor, Khanna, Pandey, Trivedi — carries ~30x the Warranty & Repair volume of the rest of Chat. Matches what your Ops manager flagged before the exports were sent: that rota gets the angriest customers by design."),
      p("Remove those 14 and rank what's left — Chat, Email, Voice, Billing on comparable queues, 15+ survey responses each — and a real, closable gap appears: the ten lowest average 3.52 CSAT against 3.66 for the rest of the pool. That gap training can move; the other group's can't — only the queue can.", { after: 140 }),

      p("Two things worth your attention that nobody asked me to look for", { bold: true, size: 22, after: 60 }),
      bullet("Six orders received both a refund and a replacement on the same ticket. Policy §5 requires same-day escalation to Team Lead + Finance when that happens — worth a quick check."),
      bullet("Arjun's Rs 2,500-per-replacement figure is off: your own policy prices a replacement at unit cost + Rs 340, ~Rs 1,800 on average. The underlying spike is real (~60/month in summer to 300+ in Jan–Feb) — the per-unit number just needs fixing before it's used in a business case."),
      p("Also: CSAT bottomed out in February at 2.95 and had already recovered to 3.40 by June, three months before this email. \"Sliding since festive season\" describes the trough, not where things stand now.", { after: 140 }),

      p("What I'd do with this", { bold: true, size: 22, after: 60 }),
      bullet("Point the Rs 4,00,000 at the corrected bottom 10, not the raw ranking."),
      bullet("Give the triage rota and Logistics/Returns/Warranty a staffing conversation, not a training line item."),
      bullet("Same logic for the Diwali bonus: easy-queue agents will always out-rank hard-queue agents doing good work. Use the comparable-pool ranking."),

      new Paragraph({ spacing: { before: 240, after: 0 }, border: { top: { style: BorderStyle.SINGLE, size: 2, color: "C9C2B2" } }, children: [
        new TextRun({ text: "Full agent-by-agent numbers, the excluded groups, and the data-quality issues found along the way are in the attached dashboard. Happy to walk through any of it.", font: FONT, size: 18, italics: true, color: "5C5647" })
      ] }),
    ],
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync("/home/claude/work/vireo-dashboard/memo-to-priya.docx", buf);
  console.log("written");
});
