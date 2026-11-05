// CLI: validate all curriculum content and print a summary.
// Usage: npm run validate:content [-- --strict]   (--strict fails on warnings too)
import { resolve } from "node:path";
import { formatIssues, loadContent } from "../src/content/load.ts";

const root = resolve(import.meta.dirname, "..");
const strict = process.argv.includes("--strict");
const content = loadContent(root);
const errors = content.issues.filter((i) => i.severity === "error");
const warnings = content.issues.filter((i) => i.severity === "warning");

const s = content.index.stats;
console.log(
  `Content: ${s.stages} stages, ${s.modules} modules, ${s.concepts} concepts, ${s.lessons} lessons, ` +
    `${s.items} assessment items, ${s.projects} projects, ${s.interviewQuestions} interview questions, ${s.glossaryTerms} glossary terms`,
);
if (warnings.length) console.log(`\n${warnings.length} warning(s):\n${formatIssues(warnings)}`);
if (errors.length) console.log(`\n${errors.length} error(s):\n${formatIssues(errors)}`);
if (errors.length || (strict && warnings.length)) process.exit(1);
console.log("\nContent is valid.");
