ED PACKAGE BUILDER v16 — PORTABLE BUILD SOURCE + LOCAL PILOT

WHAT THIS RELEASE DELIVERS
- Original application features from v15, including offline case import, evidence review, invoice reconciliation, integrity checks and document generation.
- Fixes bundled-template lookup for PyInstaller one-folder mode.
- Adds a Windows CI build workflow in .github/workflows/build-windows.yml. It runs tests, packages a portable Windows app folder and attaches the ZIP to the workflow run.
- Adds a read-only local-pilot validator and tests; no vendor images are uploaded.

IMPORTANT: THIS IS BUILDABLE SOURCE, NOT AN ALREADY-VERIFIED WINDOWS EXECUTABLE.
The Windows workflow has not been run or tested on the user's computer. A portable folder can be copied/extracted and launched by double-clicking ED_Package_Builder.exe after a successful Windows build. Enterprise device restrictions may still block execution.

HOW TO BUILD WITHOUT INSTALLING PYTHON ON THE WORK COMPUTER
1. Use an authorized GitHub repository with GitHub Actions enabled. Do not upload private vendor photos or case data to the repository.
2. Upload the source code and included original DOCX template. Keep .github/workflows/build-windows.yml intact.
3. Trigger the Build portable Windows application workflow, then download the artifact from the completed run.
4. Unzip and test the executable folder on an approved Windows device. A Python install is not required to RUN the built app.
5. If IT blocks unsigned executables, seek ordinary approval; do not bypass security controls.

LOCAL AI REMAINS OPTIONAL AND IS NOT INCLUDED IN THE BUILD
- v15's Ollama adapter only runs when an approved localhost model is installed separately.
- The EXE does NOT include trained model weights or a model runtime. Do not claim automatic load-stage recognition works until a real model is bundled and validated against labeled vendor examples.
- No approved local model is available in this runtime, and Windows compatibility was not tested here.
- No background internet uploads or cloud fallback exist in the included adapter.

PDF OUTPUT
- The application can create Word drafts. Automatic PDF conversion may still need LibreOffice on the computer; the Windows build does not bundle LibreOffice. This remains an installation-free gap to resolve.

PILOT
Run `python pilot_preflight.py /path/to/Workorder_EXAMPLE_Documents.zip` in a development environment to generate a read-only inventory summary. This does not claim recognition accuracy.

NEXT ACCEPTANCE GATES
- Successful Windows build artifact and Windows launch smoke test.
- Model-selection, licensing and bundling feasibility on hardware.
- Human-verified labels for representative 7876213 photos, then precision/recall and load/receipt matching metrics.
- Built-in PDF generation, full page visual QA, model inference rate and offline status validation.
