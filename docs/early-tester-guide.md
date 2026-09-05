# MaterialScope — Early Tester Guide

**Early feedback round for materials characterization workflows**

MaterialScope is an early-stage software platform designed to make materials characterization workflows more organized, reproducible, and practical.

---

## Setup

Follow the [English setup instructions](../README.md#run-locally) or [Türkçe kurulum yönergeleri](../README.tr.md#yerel-kurulum), then open the local Dash application at [127.0.0.1:8050](http://127.0.0.1:8050). The README is the canonical setup guide; one command starts both the interface and its API.

This walkthrough targets Dash. The retained Windows installer starts Streamlit, and the experimental Electron shell uses a separate backend-only launch path. Their screens and capabilities differ.

## What is MaterialScope?

MaterialScope supports workflows around common materials characterization methods:

- XRD
- FTIR
- Raman
- DSC
- TGA
- DTA

The goal is to reduce fragmentation between vendor software, spreadsheets, plotting tools, database or library tools, and separate reporting documents. MaterialScope is intended to help users keep data, processing decisions, visualizations, comparisons, and report outputs closer together in one workflow.

## What problem is it trying to solve?

Characterization workflows often require users to:

- Import data in different formats
- Clean or reorganize data manually
- Plot results in separate tools
- Compare multiple samples manually
- Export figures for reports, presentations, or papers
- Keep track of different project files
- Move between vendor software, Excel, Origin, Python, and reporting tools

MaterialScope aims to bring these steps into a cleaner and more reproducible workflow. The current testing round is focused on whether this direction is practical for real characterization work, not on presenting a finished commercial product.

## What should testers focus on?

### General usability

- Is the interface understandable?
- Is the workflow clear?
- Do you understand what each section is for?
- Does anything feel confusing or unnecessary?

### Scientific usefulness

- Would this help with real characterization work?
- Are the plots useful?
- Are important analysis steps missing?
- Does the workflow match how researchers or lab users actually work?

### Data workflow

- Is importing or working with data clear?
- Is sample comparison useful?
- Are export options practical?
- Would this help reduce manual work?

### Visual quality

- Are the plots clean enough for reports, presentations, or publications?
- Do the figures feel scientific and professional?
- What would make them better?

## Suggested 10-minute testing flow

1. Open the Dash app after setup. On the import/home page, load the DSC polymer-melting sample, or upload [dsc_polymer_melting.csv](../sample_data/dsc_polymer_melting.csv).
2. Review the detected DSC modality, temperature/signal columns, units, and import warnings.
3. Open DSC, run the analysis, inspect the plot and detected features, and save the result to the workspace.
4. Import a second DSC dataset, such as [dsc_HDPE_melting_10Kmin.csv](../test_data/dsc_HDPE_melting_10Kmin.csv), then inspect its metadata and run/save its analysis too.
5. Open Compare, choose DSC, select both datasets, inspect the overlay, and save the comparison workspace. These example files use different heat-flow units (mW/mg versus mW); use this step to assess the interface, not to compare amplitudes quantitatively. Scientific comparisons require compatible units and processing choices.
6. Open Export, select saved results, and download a data export or report. Check that the output contains the intended results and labels.
7. On Project, download a `.scopezip` archive and keep it on disk before stopping the server. A result saved inside the running workspace is not a disk backup.
8. Note confusing controls, missing features, failed downloads, or questionable scientific results, including the sample filename and steps to reproduce.
9. Fill out the feedback form below. You can repeat the workflow with your own data or another supported modality.

## What kind of feedback is most useful?

Honest critical feedback is preferred over general praise. Specific comments are the most helpful because they point directly to workflow, scientific, or usability issues that can be improved.

Useful examples:

- "This workflow is confusing because..."
- "This feature would not be useful in a real lab because..."
- "For XRD, FTIR, or TGA analysis, this step is missing..."
- "The plot should include..."
- "I would expect this export option..."
- "This would be more useful if..."

## Known limitations

MaterialScope is still early-stage. Some features may be incomplete, experimental, or not fully polished. The goal of this testing round is not to evaluate a finished commercial product, but to understand whether the workflow direction is useful for real users.

Workspaces are held in memory and are lost when the server restarts unless you download and later reopen a project archive. Keep original measurement files separately. Configured library and literature features may contact network services; local-first does not guarantee fully offline operation.

Library, license, kinetics, and deconvolution have Streamlit pages without equivalent Dash pages. Kinetics and deconvolution are preview features on that legacy surface. The [parity inventory](streamlit-parity-inventory.md) records the differences; it does not authorize Streamlit removal or certify scientific results. Check units, calibration, and interpretation independently.

Please focus on:

- Workflow logic
- Scientific usefulness
- Missing features
- Confusing parts
- Usability problems
- Plot and report quality
- Real-world applicability

## Feedback form

Please submit feedback using this form:

https://docs.google.com/forms/d/e/1FAIpQLSc02aKo4FFWcmXqgznLtCK0P-sNIygD9PXybNiODP1A4UENxw/viewform

Estimated time: 10-15 minutes.

## Follow-up

If you are open to a short follow-up conversation, please leave your name, email, or LinkedIn profile in the form.

Your feedback will directly help shape the next development steps of MaterialScope.
