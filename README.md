# Wirewise

> A visual inspection and learning tool that uses computer vision and Gemma 4 to compare real breadboard circuit photos against target circuit schematics.

## Team

**Team Name:** Team Vitality


| Member | Contribution   |
| ------ | -------------- |
| Aakaash Pavangat | **Frontend Lead & Interactive UI:**  Built the Next.js App Router interface, interactive Canvas/SVG annotation overlays for bounding polygons, landmark calibration controls, and the evidence-based findings report UX. | |
| Tanala Phanendra | **AI Vision Pipeline Lead:** Integrated Gemma 4 multimodal vision, designed the server-side provider adapter architecture, optimized prompt engineering for structured detection outputs, and implemented the demo mode fallback. |
| Mohammad Liyakat Ali |  |
| Govind Shrundan Reddy | [Contribution] |


## Problem Statement

### The Problem

Electronics hobbyists, students, and educators working with solderless breadboards frequently run into small, hard-to-spot wiring errors. Miscounting a breadboard row by a single pin, placing a component across the wrong power rail, or inserting a polarized diode backward can cause a circuit to fail silently or behave unpredictably.

Tracing physical circuits manually against a schematic is time-consuming and error-prone, especially for beginners. While modern software development relies on automated visual diffs and linters to catch mistakes instantly, physical prototyping lacks a reliable way to compare an assembled physical circuit against an intended wiring plan. Traditional computer vision struggles with the complex angles and overlapping wires of real-world breadboards, while raw AI vision models risk hallucinating connections or making unverified safety assumptions if relied on blindly.

### Why We Chose This Problem

Hardware debugging remains one of the steepest learning curves in STEM education and maker environments. Misplaced wires often lead to hours of unnecessary troubleshooting, student frustration, and abandoned projects.

We selected this problem to demonstrate how open-weight vision models like Gemma 4 can be combined with deterministic graph logic to solve a genuine physical-world friction point. By keeping the AI focused on visual proposal and using deterministic graph algorithms for the actual circuit comparison, we create a reliable, visual linter for physical hardware that accelerates learning without compromising safety.



## Solution Overview

Wirewise is a web-based visual inspection and learning application that compares a photograph of a physical, low-voltage breadboard circuit against a verified schematic template.

### Core Workflow

Wirewise guides users through a structured, human-in-the-loop inspection process:

1. **Interactive Calibration**  
   Upload a top-down photo of your breadboard and align key grid landmarks to correct perspective distortion using OpenCV.

2. **AI-Assisted Vision Proposals**  
   Gemma 4 analyzes the calibrated image to propose candidate components, wire endpoints, labels, and visible orientation with confidence scores.

3. **Human Verification**  
   Confirm, reject, or adjust the proposed observations. No uncertain model guess is ever silently accepted as a confirmed connection without user approval.

4. **Deterministic Graph Comparison**  
   Confirmed observations are compiled into an electrical connection graph and evaluated against the target template using NetworkX graph matching.

5. **Evidence-Based Reporting**  
   Wirewise overlays findings—such as missing wires, misplaced rows, or polarity errors—directly onto the original photo with clear explanations and pinpointed image regions.


### Key Features

* **Interactive Perspective & Grid Calibration**  
  Uses OpenCV 4-point landmark alignment to correct lens distortion and map physical breadboard coordinates directly onto top-down circuit photos.

* **Gemma 4 AI Vision Proposals**  
  Leverages Gemma 4 multimodal vision to identify component types, pin markings, wire endpoints, and polarity orientation with confidence scores and bounding polygons.

* **Human-in-the-Loop Verification System**  
  Provides an interactive review interface that requires explicit user confirmation or correction before turning visual detections into electrical connections.

* **Deterministic Graph Engine & Evidence Overlay**  
  Compiles verified connections into NetworkX graphs to evaluate expected vs. observed wiring, overlaying color-coded findings directly onto photo regions with plain-language explanations.
## Innovation and Differentiation

[Explain what is innovative about the approach and how it differs from existing or conventional solutions.]

## Technical Implementation

### Architecture

[Add the system architecture or workflow Mermaid diagram here.]

### Technology Stack


| Category        | Technologies                |
| --------------- | --------------------------- |
| Frontend        | [Technologies / N/A]        |
| Backend         | [Technologies / N/A]        |
| Database        | [Technologies / N/A]        |
| AI / ML         | [Models / frameworks / N/A] |
| Infrastructure  | [Technologies / N/A]        |
| APIs / Services | [Services / N/A]            |


If a category or technology is not implemented in the project, specify `N/A` instead of leaving the field blank.

### How It Works

[Explain the major components of the system and how they interact.]

### Technical Decisions

[Explain important architectural, algorithmic, or engineering decisions made during development.]

## Implementation During the Hackathon

[Describe what the team built during the Hack Day and the major functionality or components completed during the event.]

### Team Contributions

- **[Member Name]:** [Contribution]
- **[Member Name]:** [Contribution]
- **[Member Name]:** [Contribution]
- **[Member Name]:** [Contribution]

## Working Application

**Live Application:** [Live URL]

[Briefly explain how the deployed application can be accessed and what functionality can be tested.]

The submitted application should be functional and accessible through the provided link where applicable.

## Demo Video

**Demo Video:** [Video URL]

[Provide a short demonstration of the working project, covering the main user flow and important functionality.]

## Open Source and AI Usage

### AI / Models

- **[Model]:** [How it is used]

### Open Source Components

- **[Library / Framework]:** [Purpose]
- **[Dataset]:** [Purpose]
- **[API / Service]:** [Purpose]

[Include relevant licenses, attribution, and acknowledgements for external components.]

## Setup and Usage

### Prerequisites

- [Requirement]
- [Requirement]

### Installation

```bash
git clone [repository-url]
cd [project-directory]
[installation-command]
```

### Environment Variables

```env
[VARIABLE_NAME]=[value]
```



### Running the Project

```bash
[run-command]
```

### Usage

[Explain the basic steps required to use the project.]

## Devpost Submission

**Devpost Project:** [Devpost Project URL]

[Add the link to the team's Devpost submission. Ensure the Devpost project page is complete and contains the required project information, links, media, and team details.]

## Credits and License

### Credits

[Credit libraries, frameworks, datasets, models, APIs, contributors, and other external resources used.]

### License

[License name and/or link.]

## Submission Checklist

- [ ] Project title and description added
- [ ] All team members listed
- [ ] Problem clearly explained
- [ ] Reason for choosing the problem explained
- [ ] Solution and key features documented
- [ ] Innovation and differentiation explained
- [ ] Architecture included
- [ ] Technical implementation documented
- [ ] Work completed during the hackathon documented
- [ ] Team contributions documented
- [ ] Working application is functional
- [ ] Live application link added where applicable
- [ ] Demo video added
- [ ] AI and open-source components documented
- [ ] Setup and usage instructions tested
- [ ] Challenges and learnings documented
- [ ] Devpost submission completed
- [ ] Devpost link added
- [ ] Credits added
- [ ] License added
- [ ] Repository is organized and complete
