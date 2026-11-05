# Groundwork

**A local-first, zero-cost, interactive learning platform that takes you from absolute beginner to production-ready
engineer across Python, software engineering, data, machine learning, generative AI, RAG and agentic AI.**

Understand deeply → visualise → practise → debug → build → test → master. Everything runs on your computer: the
lessons, a real Python interpreter (in your browser), your progress and the tests. No accounts, no paid APIs, no
tracking.

<!-- status:start -->
<!-- status:end -->

## Quick start

Requirements: **Node.js 22.12+** (with npm) and a modern browser. Python is optional (only for the local project kits).

```powershell
npm install        # installs dependencies and copies the Python runtime into public/pyodide
npm run dev        # open http://localhost:5173
```

For the faster production build:

```powershell
npm run start      # builds, then serves on http://localhost:4173 and opens your browser
```

Your progress is saved in this browser automatically. Use **Settings → Export progress** for backups.

## What you can do

* **Learn** — lessons explain what, why and how it works inside, with a beginner view and optional deep dives,
  executed code examples, misconception call-outs, cheat sheets and official sources.
* **See it** — step through real Python execution (names → objects, frames, output), and explore interactive models:
  HTTP lifecycle, RAG pipeline, agent tool loop, MCP messages, CI/CD, vector similarity, Big-O growth, BFS/DFS,
  gradient descent, SQL joins, neural networks and attention. (**Visual explorer**.)
* **Practise** — predict outputs, answer targeted questions, write and debug code that is graded by automated tests in
  the browser, arrange Parsons problems, and explain concepts against a rubric. Every wrong answer explains the
  misconception behind it; Python errors come with beginner explanations.
* **Prove mastery** — each lesson ends with a mastery check of new questions (one attempt, no hints, includes coding).
* **Remember** — spaced reviews (1, 3, 7, 16, 35, 90 days) bring concepts back as you start to forget them.
* **Follow a path** — ten goal-based paths (Python, backend, data science, data engineering, ML engineering, GenAI,
  RAG, agentic AI, production AI, interviews) generated from one prerequisite graph; skip what you know with a
  diagnostic.
* **Explore the map** — ~400 concepts across 21 stages with an interactive prerequisite graph and an accessible list
  view; concepts without a full lesson yet show an outline (key ideas, misconceptions, prerequisites, official sources).
* **Build** — progressive projects from a browser calculator to agents with human approval, MCP servers and a
  production AI service, each with acceptance criteria, milestones, automated tests and a rubric.
* **Prepare for interviews** — a categorised question bank with model answers, key points, pitfalls, follow-ups and
  revision scheduling.
* **Search everything** (Ctrl+K), use the **playground**, keep **snippets**, and manage **themes**, motion, backups and
  storage in **Settings**.

## Documentation

| Document | Contents |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design, decisions and trade-offs |
| [CURRICULUM.md](CURRICULUM.md) | Stages, prerequisite philosophy, mastery rules |
| [CURRICULUM_AUDIT.md](CURRICULUM_AUDIT.md) | How the curriculum was derived, coverage matrix, gaps |
| [CONTENT_SCHEMA.md](CONTENT_SCHEMA.md) | Content format, validation, how to add lessons |
| [TESTING.md](TESTING.md) | Test strategy and commands |
| [SECURITY.md](SECURITY.md) | Security model, privacy and limitations |
| [COST_AND_LICENSES.md](COST_AND_LICENSES.md) | ₹0 cost breakdown, licences, internet and hardware needs |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development guidelines |
| [ROADMAP.md](ROADMAP.md) | Milestones, implementation status, what remains |

## Development

```powershell
npm run check            # validate content, type-check, lint, unit + content tests, production build
npm run test:e2e         # Playwright end-to-end tests in your installed Edge (PW_CHANNEL=chrome for Chrome)
npm run test:projects    # verify local project kits with Python (uses .venv if present)
npm run check:links      # re-check every cited URL
npm run report:coverage  # regenerate the coverage tables in CURRICULUM_AUDIT.md and ROADMAP.md
```

Adding a lesson is a YAML file — see [CONTENT_SCHEMA.md](CONTENT_SCHEMA.md#worked-example-adding-a-lesson).

## Licence

Code: MIT. Dependencies are listed with their licences in [COST_AND_LICENSES.md](COST_AND_LICENSES.md).






## Setup Guide--
# AI Learning Platform

## Getting Started

Welcome to the AI Learning Platform!

This guide explains how to download, install, configure, and run the platform on your local computer.

Follow the instructions step by step. No prior experience with this project is required.

---

## 1. Prerequisites

Before running the project, make sure you have the following software installed.

| Software | Requirement | Purpose |
|---|---|---|
| Node.js | Version 22.12 or newer | Runs the development environment |
| npm | Included with Node.js | Installs project dependencies |
| Git | Latest stable version | Required only when cloning the repository |
| Visual Studio Code | Recommended | Code editor |

### Download the required software

- **Node.js:** https://nodejs.org/en/download
- **Git:** https://git-scm.com/downloads
- **Visual Studio Code:** https://code.visualstudio.com/

### Important: Node.js installation

During Node.js installation:

1. Use the Windows installer (64-bit).
2. Keep the option to add Node.js to the system PATH enabled.
3. Complete the installation.
4. Close and reopen your terminal or VS Code.

npm is automatically installed with Node.js. You do not need to install it separately.

### Verify the installation

Open PowerShell or the VS Code terminal and execute:

~~~powershell
node -v
npm -v
git --version
~~~

You should see version numbers.

**Note:** Git is required only if you are cloning the repository. If you downloaded the project as a ZIP file, Git is not necessary.

If `node` or `npm` is not recognized, resolve the Node.js PATH configuration before proceeding.

---

## 2. Get the Project Code

You can obtain the project using either of the following methods.

### Option A: Clone the GitHub repository

Open PowerShell and execute:

~~~powershell
cd "$HOME\Downloads"
git clone <YOUR_REPOSITORY_URL>
~~~

Replace `<YOUR_REPOSITORY_URL>` with the actual repository URL.

Navigate into the project directory:

~~~powershell
cd AI_learning_platform
~~~

If your repository uses a different folder name, navigate into that folder instead.

### Option B: Download or copy the project ZIP

1. Download the project ZIP file.
2. Locate the downloaded ZIP file.
3. Right-click it and select **Extract All**.
4. Open the extracted folder.
5. Locate the `AI_learning_platform` directory.

You should see project files and folders similar to:

~~~text
AI_learning_platform/
│
├── package.json
├── package-lock.json
├── index.html
├── src/
├── content/
├── public/
├── scripts/
├── tests/
├── README.md
└── ...
~~~

**Important:** Make sure you open the actual project directory containing `package.json`, not its parent directory.

---

## 3. Open the Project in Visual Studio Code

1. Open Visual Studio Code.
2. Select **File → Open Folder**.
3. Navigate to the `AI_learning_platform` directory.
4. Select the folder and open it.
5. Open the integrated terminal using:

   **Terminal → New Terminal**

The terminal should open inside your project directory.

### Verify the project directory

Execute:

~~~powershell
Test-Path .\package.json
~~~

Expected output:

~~~text
True
~~~

If the output is `False`, you are in the wrong directory. Navigate to the directory containing `package.json`.

---

## 4. First-Time Project Setup

**This section needs to be completed only once when setting up the project on a new computer.**

### Step 1: Install project dependencies

In the VS Code terminal, execute:

~~~powershell
npm ci
~~~

This command:

- Reads the `package-lock.json` file.
- Downloads the required project dependencies.
- Installs the exact dependency versions specified in the lockfile.
- Creates the `node_modules` directory.

Wait until the installation finishes successfully.

**Important:**

- An active internet connection is required for downloading dependencies.
- Do not delete or modify `package-lock.json` unnecessarily.
- You do not need to execute `npm ci` every time you start the application.

If installation fails, check the error message before proceeding.

### Step 2: Start the development server

After dependencies have been installed, execute:

~~~powershell
npm run dev
~~~

The development server should start successfully.

You should see output similar to:

~~~text
VITE ready

Local: http://localhost:5173/
~~~

### Step 3: Open the application

Open your web browser and navigate to:

**http://localhost:5173/**

The AI Learning Platform should now be accessible locally.

Congratulations! Your application is running.

---

## 5. How to Run the Project Next Time

Once the initial setup is complete, you do not need to repeat the installation process every time.

Follow these steps whenever you want to use the platform:

1. Open Visual Studio Code.
2. Open the `AI_learning_platform` project folder.
3. Open a new terminal.
4. Execute the following command:

~~~powershell
npm run dev
~~~

5. Open the local URL displayed in the terminal, usually:

   http://localhost:5173/

That's it! The application is ready to use.

**You do not need to run `npm ci` again for normal startup.**

---

## 6. How to Stop the Application

When you want to stop the development server:

1. Return to the VS Code terminal where the application is running.
2. Press `Ctrl + C`.
3. Confirm if PowerShell asks for confirmation.

The development server will stop.

You can close VS Code afterward.

---

## 7. Useful Development Commands

The following commands may be useful when working with the project.

| Command | Purpose | When to use |
|---|---|---|
| `npm ci` | Installs dependencies from the lockfile | First-time setup or clean reinstall |
| `npm run dev` | Starts the development server | Whenever you want to run the platform |
| `npm run build` | Creates a production build | When checking production compilation |
| `npm run check` | Runs the configured project checks | During development and validation |

**Note:** Additional commands may be available in `package.json`. Check its `scripts` section for the complete list.

---

## 8. Do You Need Python Installed?

No. Python is not required to start or use the core learning platform.

The platform uses **Pyodide** to execute Python code directly in the browser for interactive Python learning exercises.

You do not need:

- A separate Python installation for the core application.
- A Python virtual environment (`venv`).
- A local Python interpreter to start the development server.

Python installation may be useful later if you want to work with optional local Python project kits or Python development tools.

---

## 9. Troubleshooting

### Problem 1: `npm is not recognized`

**Error:**

~~~text
npm : The term 'npm' is not recognized...
~~~

**Possible cause:** Node.js is not installed correctly or its installation directory is missing from the system PATH.

**Solution:**

1. Verify Node.js installation:

   ~~~powershell
   node -v
   ~~~

2. Check whether Node.js is available at:

   ~~~text
   C:\Program Files\nodejs\
   ~~~

3. If necessary, add that directory to the Windows PATH environment variable.
4. Restart VS Code.
5. Open a new terminal and try again.

### Problem 2: `node is not recognized`

**Possible cause:** Node.js is not installed or its PATH configuration is incorrect.

**Solution:**

1. Install Node.js 22.12 or newer.
2. Ensure the PATH option is enabled during installation.
3. Restart your terminal or VS Code.
4. Verify using:

   ~~~powershell
   node -v
   npm -v
   ~~~

### Problem 3: `package.json` not found

**Possible cause:** You are executing commands from the wrong directory.

**Solution:**

Navigate to the project directory containing `package.json`.

Verify using:

~~~powershell
Test-Path .\package.json
~~~

The expected result is `True`.

### Problem 4: Dependency installation fails

**Possible causes:**

- Internet connection problems.
- npm registry connectivity issues.
- Incorrect Node.js or npm installation.
- Dependency installation errors.

**Solution:**

Check the complete error message and resolve the reported issue.

If you need to reinstall dependencies, you can remove the existing `node_modules` directory and execute:

~~~powershell
npm ci
~~~

Do not delete `package-lock.json` as a troubleshooting shortcut.

### Problem 5: Port 5173 is already in use

**Possible cause:** Another development server is already using the port.

**Solution:**

- Check whether another instance of the application is running.
- Stop that instance using `Ctrl + C`.
- Alternatively, Vite may offer another available local port in its terminal output.

Use the URL displayed by Vite.

### Problem 6: Application is not opening in the browser

**Check the following:**

1. Is the development server still running?
2. Does the terminal show a successful Vite startup?
3. Are you opening the correct local URL?
4. Does the terminal show any errors?

---

## 10. Quick Reference

### First-time setup

Execute these commands in order:

~~~powershell
# 1. Navigate to the project directory
cd "PATH_TO_AI_LEARNING_PLATFORM"

# 2. Verify the project directory
Test-Path .\package.json

# 3. Install dependencies
npm ci

# 4. Start the development server
npm run dev
~~~

### Normal startup (every subsequent time)

~~~powershell
# Start the application
npm run dev
~~~

### Stop the application

~~~text
Press Ctrl + C in the terminal.
~~~

---

## 11. Important Notes

- Keep Node.js installed on your computer.
- Keep `package.json` and `package-lock.json` in the project.
- Do not commit the `node_modules` directory to Git.
- Do not run `npm ci` every time you start the application.
- If dependencies change in a new version of the project, run `npm ci` again.
- Keep an active internet connection for initial dependency installation and any features that require external resources.
- The development server must remain running while you use the local application.

---

**You're all set!**

Follow the first-time setup instructions once, and use `npm run dev` whenever you want to launch the AI Learning Platform again.