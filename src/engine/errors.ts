// Beginner-friendly explanations for Python errors. Specific message patterns
// are checked first, then the general explanation for the error type.
import type { PyError } from "../python/types";

export interface ErrorExplanation {
  title: string;
  meaning: string;
  fixes: string[];
  learnMore?: { label: string; conceptId: string };
}

interface Pattern {
  type: string | string[];
  match?: RegExp;
  explain: (m: RegExpMatchArray | null, error: PyError) => ErrorExplanation;
}

const patterns: Pattern[] = [
  {
    type: "NameError",
    match: /name '(.+?)' is not defined/,
    explain: (m, e) => {
      const suggestion = /Did you mean: '(.+?)'\?/.exec(e.traceback)?.[1];
      return {
        title: `Python doesn't know any name called "${m?.[1]}"`,
        meaning: `When Python reached line ${e.line ?? "?"}, it looked up "${m?.[1]}" and found nothing with that name.`,
        fixes: [
          ...(suggestion ? [`Did you mean "${suggestion}"? Python spotted a similar name.`] : []),
          "Check spelling and capitalisation — names must match exactly.",
          "Make sure the name is assigned on an earlier line; programs run top to bottom.",
          `If you meant the text "${m?.[1]}", put it in quotes.`,
        ],
        learnMore: { label: "Variables and assignment", conceptId: "python.variables" },
      };
    },
  },
  {
    type: "UnboundLocalError",
    explain: () => ({
      title: "A local variable was read before it was assigned",
      meaning: "Inside a function, assigning to a name anywhere makes it local for the whole function. You read it before that assignment ran.",
      fixes: ["Pass the value in as a parameter and return the new value.", "Assign the name before reading it inside the function."],
      learnMore: { label: "Scope and namespaces", conceptId: "python.scope" },
    }),
  },
  {
    type: "TypeError",
    match: /can only concatenate str \(not "(\w+)"\) to str|unsupported operand type\(s\) for \+: '(\w+)' and '(\w+)'/,
    explain: (m) => ({
      title: "Mixing text and numbers with +",
      meaning: `\`+\` can add two numbers or join two strings, but not one of each${m?.[1] ? ` (here: str and ${m[1]})` : ""}. Python won't guess which you meant.`,
      fixes: [
        'To join, convert the number: "Age: " + str(age), or use an f-string: f"Age: {age}".',
        "To add, convert the text: int(text) + 1 (text must contain a whole number).",
      ],
      learnMore: { label: "Types and type conversion", conceptId: "python.type-conversion" },
    }),
  },
  {
    type: "TypeError",
    match: /'(\w+)' object is not callable/,
    explain: (m) => ({
      title: `You tried to call a ${m?.[1]} as if it were a function`,
      meaning: "Parentheses after a name mean “call this function”, but the name refers to a value that cannot be called.",
      fixes: [
        "Did you reuse a built-in name like print, str, list, sum or input for a variable? Rename your variable.",
        "Did you forget an operator? `2(3 + 4)` needs `2 * (3 + 4)`.",
      ],
      learnMore: { label: "Variables and assignment", conceptId: "python.variables" },
    }),
  },
  {
    type: "TypeError",
    match: /takes (\d+) positional arguments? but (\d+) (?:were|was) given|missing (\d+) required positional argument/,
    explain: () => ({
      title: "Wrong number of arguments in a function call",
      meaning: "The call passed a different number of values than the function's parameters expect.",
      fixes: ["Compare the call with the function's def line and count the parameters.", "For methods, remember self is passed automatically."],
      learnMore: { label: "Defining and calling functions", conceptId: "python.functions" },
    }),
  },
  {
    type: "TypeError",
    match: /'NoneType' object is not (subscriptable|iterable)/,
    explain: () => ({
      title: "You used None as if it were a list or other collection",
      meaning:
        "A value you expected to be a collection is actually None — very often because a function has no return statement, or because a method like list.sort() returns None.",
      fixes: [
        "Check the function that produced the value returns something.",
        "Don't assign the result of in-place methods: write lst.sort(), not lst = lst.sort().",
      ],
      learnMore: { label: "Defining and calling functions", conceptId: "python.functions" },
    }),
  },
  {
    type: "TypeError",
    match: /'(\w+)' object is not iterable/,
    explain: (m) => ({
      title: `A ${m?.[1]} can't be looped over`,
      meaning: "for loops (and functions like list() or sum()) need an iterable — something like a list, string, range or dict.",
      fixes: ["To repeat n times, loop over range(n) instead of n.", "Check that the variable holds the collection you expect."],
      learnMore: { label: "For loops and range", conceptId: "python.for-loops" },
    }),
  },
  {
    type: "ValueError",
    match: /invalid literal for int\(\) with base 10: '(.*)'/,
    explain: (m) => ({
      title: `"${m?.[1]}" isn't a whole number`,
      meaning: 'int() can only convert text that looks like a whole number, such as "42" or "-7".',
      fixes: [
        'For decimals, use float() first: int(float("3.5")).',
        "Strip spaces or validate the input before converting.",
        "Use try/except ValueError to handle bad input.",
      ],
      learnMore: { label: "Types and type conversion", conceptId: "python.type-conversion" },
    }),
  },
  {
    type: "ZeroDivisionError",
    explain: () => ({
      title: "Division by zero",
      meaning: "Dividing (/, //) or taking a remainder (%) by zero is undefined, so Python stops.",
      fixes: ["Check the divisor before dividing: if count != 0: ...", "Find out why the divisor is zero — an empty list's length, perhaps?"],
      learnMore: { label: "Numbers and arithmetic", conceptId: "python.numbers" },
    }),
  },
  {
    type: "IndexError",
    explain: () => ({
      title: "Index out of range",
      meaning: "You asked for a position that doesn't exist. Indexes run from 0 to len(seq) - 1.",
      fixes: ["The last item is seq[-1] or seq[len(seq) - 1], not seq[len(seq)].", "Check loops for off-by-one errors.", "Check the sequence isn't empty."],
      learnMore: { label: "Lists", conceptId: "python.lists" },
    }),
  },
  {
    type: "KeyError",
    explain: (_m, e) => ({
      title: `The dictionary has no key ${e.message}`,
      meaning: "d[key] raises KeyError when the key is missing. Keys must match exactly, including type and case.",
      fixes: ["Use d.get(key, default) when a key may be missing.", "Check with if key in d: first.", "Print d.keys() to see what is actually there."],
      learnMore: { label: "Dictionaries", conceptId: "python.dictionaries" },
    }),
  },
  {
    type: "AttributeError",
    match: /'NoneType' object has no attribute/,
    explain: () => ({
      title: "You called a method on None",
      meaning: "The object is None, usually because a function returned nothing or an in-place method returned None.",
      fixes: ["Check what the previous step returned.", "Don't chain after in-place methods such as list.append() or list.sort()."],
    }),
  },
  {
    type: "AttributeError",
    match: /'(\w+)' object has no attribute '(\w+)'/,
    explain: (m) => ({
      title: `A ${m?.[1]} has no "${m?.[2]}"`,
      meaning: `Objects of type ${m?.[1]} don't provide an attribute or method called ${m?.[2]}.`,
      fixes: ["Check spelling and case.", `Check the object really is the type you expect — print(type(x)).`, `Use dir(x) to list what a ${m?.[1]} offers.`],
    }),
  },
  {
    type: ["ModuleNotFoundError", "ImportError"],
    explain: (_m, e) => ({
      title: "Module not available",
      meaning: `Python could not import it (${e.message}). The in-browser runtime includes the standard library; some third-party packages (numpy, pandas…) must be loaded first, and many packages are not available in the browser at all.`,
      fixes: [
        "Check the spelling of the module name.",
        "If the lesson needs a package, use its “Load packages” button (requires internet the first time).",
        "Run code that needs other packages on your own machine in a virtual environment.",
      ],
    }),
  },
  {
    type: "SyntaxError",
    match: /was never closed|unterminated string literal|unterminated triple-quoted string/,
    explain: (_m, e) => ({
      title: "Something was opened but never closed",
      meaning: `A bracket or quote that opens near line ${e.line ?? "?"} has no matching closing partner, so Python can't read the program. Nothing ran.`,
      fixes: ["Count opening and closing ( [ { and quotes on that line.", "The real problem can be on the line before the one reported."],
      learnMore: { label: "Your first program", conceptId: "python.first-program" },
    }),
  },
  {
    type: "SyntaxError",
    match: /expected ':'/,
    explain: () => ({
      title: "Missing colon",
      meaning: "Lines that start a block — if, elif, else, for, while, def, class, with, try — must end with a colon.",
      fixes: ["Add : at the end of the line that starts the block."],
      learnMore: { label: "Conditional statements", conceptId: "python.conditionals" },
    }),
  },
  {
    type: "SyntaxError",
    match: /Maybe you meant '==' or ':=' instead of '='|cannot assign to/,
    explain: () => ({
      title: "Assignment used where it isn't allowed",
      meaning: "= binds a name and must have a name on its left. To compare values, use ==.",
      fixes: ["In conditions, write if x == 5:, not if x = 5:.", "Put the name on the left: x = 5, not 5 = x."],
      learnMore: { label: "Variables and assignment", conceptId: "python.variables" },
    }),
  },
  {
    type: "SyntaxError",
    explain: (_m, e) => ({
      title: "Python couldn't read the program",
      meaning: `A SyntaxError means the text breaks Python's grammar near line ${e.line ?? "?"}, so nothing ran at all.`,
      fixes: [
        "Look at the caret (^) in the message.",
        "Check the line before as well — missing brackets or quotes often show up one line late.",
        "Check for missing colons, commas or operators.",
      ],
      learnMore: { label: "Your first program", conceptId: "python.first-program" },
    }),
  },
  {
    type: ["IndentationError", "TabError"],
    explain: (_m, e) => ({
      title: "Indentation problem",
      meaning: `Python uses indentation to group statements into blocks. Line ${e.line ?? "?"} is indented in a way that doesn't fit: ${e.message}.`,
      fixes: ["Indent the body of if/for/while/def by 4 spaces.", "Lines in the same block must line up exactly.", "Don't mix tabs and spaces."],
      learnMore: { label: "Conditional statements", conceptId: "python.conditionals" },
    }),
  },
  {
    type: "RecursionError",
    explain: () => ({
      title: "Too many nested calls",
      meaning: "A function kept calling itself (or others) without stopping until Python's safety limit was reached.",
      fixes: ["Check the base case is reachable.", "Make sure each recursive call moves closer to the base case."],
    }),
  },
  {
    type: "EOFError",
    explain: () => ({
      title: "The program asked for input that wasn't provided",
      meaning: "input() needs a line of text. In the browser, input comes from the Input box below the editor — one line per input() call.",
      fixes: ["Open the Input box and type one value per line, then run again."],
      learnMore: { label: "Input and output", conceptId: "python.input-output" },
    }),
  },
  {
    type: "OutputLimitExceeded",
    explain: () => ({
      title: "Way too much output",
      meaning: "The program printed so much that it was stopped. This almost always means a loop that never ends.",
      fixes: ["Check that the loop condition eventually becomes False.", "Make sure the loop variable is updated inside the loop."],
      learnMore: { label: "While loops", conceptId: "python.while-loops" },
    }),
  },
  {
    type: "AssertionError",
    explain: (_m, e) => ({
      title: "An assertion failed",
      meaning: e.message ? `A check in the code was false: ${e.message}` : "An assert statement found that a condition the code relies on is false.",
      fixes: ["Print the values involved just before the assert to see why."],
    }),
  },
  {
    type: "FileNotFoundError",
    explain: () => ({
      title: "File not found",
      meaning: "The path doesn't point to an existing file. In the browser runtime the file system is virtual and starts almost empty.",
      fixes: ["Check the path and the current working directory.", "Create the file first in the same program, or run locally with real files."],
      learnMore: { label: "Reading and writing files", conceptId: "python.files" },
    }),
  },
];

export function explainError(error: PyError): ErrorExplanation {
  for (const p of patterns) {
    const types = Array.isArray(p.type) ? p.type : [p.type];
    if (!types.includes(error.type)) continue;
    const m = p.match ? (p.match.exec(error.message) ?? p.match.exec(error.traceback)) : null;
    if (p.match && !m) continue;
    return p.explain(m, error);
  }
  return {
    title: `${error.type}`,
    meaning: error.message || "Python raised an exception while running your code.",
    fixes: ["Read the last line of the traceback, then the line number above it.", "Search the official docs for this exception type."],
  };
}

export const TIMEOUT_EXPLANATION: ErrorExplanation = {
  title: "The program ran too long and was stopped",
  meaning: "It didn't finish within the time limit. The usual cause is a loop whose condition never becomes False.",
  fixes: [
    "Check that something inside the loop changes the condition.",
    "Add a print() inside the loop to watch the values change.",
    "Use Step-through to see what happens on each iteration.",
  ],
  learnMore: { label: "While loops", conceptId: "python.while-loops" },
};
