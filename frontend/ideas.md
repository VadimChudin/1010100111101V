# Design Direction — Dark Mission Control

## Three stylistic approaches

### Theme Name: Dark Mission Control
Very dark graphite operations console with an icy-blue active signal, amber execution states, and a precise mono layer for telemetry. It should feel calm, intelligent, and built for watching complex work unfold.
**Probability:** 0.07

### Theme Name: Paper Circuit
Warm off-white editorial canvas with charcoal typography, cobalt diagrams, and hand-drawn annotations that make technical planning feel approachable and human.
**Probability:** 0.03

### Theme Name: Aurora Relay
Smoky slate interface with a restrained teal-to-lime signal gradient, soft glass panels, and a spatial map that feels like a live network at dusk.
**Probability:** 0.08

## Chosen approach

### Design Movement
Dark Mission Control borrows from information-dense aerospace operations rooms, modern developer tooling, and Swiss editorial systems. It translates complex agent work into a composed visual system with strong hierarchy, measurable state, and just enough atmosphere.

### Core Principles
1. **State is visible:** planning, execution, review, and completion are always legible without opening a secondary screen.
2. **Asymmetry creates focus:** the chat remains the narrative rail while the task graph gets the larger spatial canvas.
3. **Telemetry has texture:** subtle grid lines, hairline borders, grain, and mono labels make the UI feel alive without visual noise.
4. **Motion is purposeful:** transitions clarify state changes and never compete with the agent's output.

### Color Philosophy
The base is near-black graphite (#0a0e13), chosen to make the interface recede and let live work become the brightest object. Ice blue (#9de8ff) signals active intelligence and connection. Amber (#f2b35d) marks work in progress, while mint (#7de2b3) is reserved for confirmed completion. Red is only for transport or API failures. Saturation is intentionally concentrated on state-bearing elements.

### Layout Paradigm
A top status bar anchors the workspace, then an asymmetric split gives the graph approximately 58% of the desktop width and the chat 42%. On mobile, the graph becomes a concise plan strip above the conversation. Empty space is used as a quiet field around the active path rather than compressing every element into equal cards.

### Signature Elements
- A vertical signal rail with numbered agent phases and a thin cyan pulse.
- Graph nodes with a compact status glyph, eyebrow label, and one-line task title.
- A small “live link” badge that shows the transport state and last event time.

### Interaction Philosophy
Interactions should feel like operating a precise instrument: clear hover affordances, pressed states, keyboard-friendly controls, and no surprising motion. The graph responds to incoming events by highlighting the active node and subtly recentering only when the plan first arrives.

### Animation
Use 160–240ms ease-out transitions for buttons, cards, and state changes. New events enter with a short upward fade and 40ms stagger. The active graph node gets a restrained cyan ring pulse; avoid permanent glow. Respect `prefers-reduced-motion` by disabling non-essential transforms and pulsing.

### Typography System
Use **Space Grotesk** for display and UI headings, with strong 600–700 weights for hierarchy. Use **IBM Plex Mono** for run IDs, statuses, event labels, and timestamps. Body copy uses Space Grotesk 400–500 with relaxed line-height. Headings are compact and slightly tracked; mono labels are uppercase with 0.12em tracking.

### Brand Essence
A real-time command surface for teams who need to understand what an AI agent is doing, not just what it answered. **Focused, transparent, composed.**

### Brand Voice
Headlines are declarative and specific. CTAs sound like operator actions, not marketing. Microcopy names the current state plainly.

Example lines:
- “Watch the work take shape.”
- “Send a brief. Follow the run.”

### Wordmark & Logo
The mark is a compact orbital bracket: two offset corner brackets enclosing a single cyan signal dot. It works as a favicon and as the left edge of the header lockup; the wordmark is set in Space Grotesk with a deliberate split between “agent” and “room”.

### Signature Brand Color
**Signal Ice — #9DE8FF**, a pale electric cyan used sparingly for active intelligence, live transport, and graph focus.

## Style Decisions

- The phase tracker is an ownable numbered signal rail with explicit operator states rather than a generic progress stepper.
- Empty graph states still show topology through a staged execution spine, connection cues, and telemetry labels.
- Visible copy uses operator verbs and explicit state language such as “Queue a brief”, “Stream synced”, and “Waiting for input”.
