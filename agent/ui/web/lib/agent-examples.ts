export interface AgentExampleGroup {
  title: string;
  examples: { label: string; prompt: string }[];
}

// Plain-language entry points for the registered CAD, printer, and host tools.
// Prompts are drafts only; existing stage and approval gates still apply.
export const STAGE_GUIDANCE: Record<string, { intro: string; groups: AgentExampleGroup[] }> = {
  '/limb': {
    intro: 'Describe the measurements you want to change, with units. Or choose an example below and edit it before sending.',
    groups: [
      { title: 'Measurements', examples: [
        { label: 'Set my measurements', prompt: 'Set residual length to 150 mm, proximal circumference to 300 mm, and distal circumference to 240 mm. Check the values, then update the limb.' },
        { label: 'Change one value', prompt: 'Change only the proximal circumference to 310 mm. Keep my other measurements.' },
        { label: 'Check my inputs', prompt: 'Check my current limb measurements for missing or inconsistent values before making any changes.' },
        { label: 'Help me choose', prompt: 'Help me understand the optional limb measurements. Ask me which one I want to adjust before changing anything.' },
      ] },
      { title: 'Explore & continue', examples: [
        { label: 'About the starting shape', prompt: 'Tell me about the standard residual limb template and its default measurements.' },
        { label: 'Read current dimensions', prompt: 'Show the dimensions of my current residual limb revision.' },
        { label: 'See saved versions', prompt: 'List the available parts and saved revisions.' },
        { label: 'Continue to socket', prompt: 'Confirm my current limb and take me to the socket stage.' },
      ] },
    ],
  },
  '/socket': {
    intro: 'Tell me how you want to refine the socket. You can also ask about its dimensions or how it relates to the limb.',
    groups: [
      { title: 'Refine the socket', examples: [
        { label: 'Change wall thickness', prompt: 'Set the current socket wall thickness to 5 mm. Keep the limb unchanged.' },
        { label: 'Read socket dimensions', prompt: 'Show the dimensions of my current socket.' },
        { label: 'Check the relationship', prompt: 'Check my current socket against my current limb. Explain the reported clearance and any overlap in plain language.' },
        { label: 'Rebuild around my limb', prompt: 'Rebuild the socket around my current limb revision, keeping the limb unchanged.' },
        { label: 'Review readiness', prompt: 'Check whether my current socket is ready for slicing and explain anything that needs adjustment.' },
        { label: 'Continue to printer', prompt: 'Confirm my current socket and take me to the printer stage.' },
      ] },
      { title: 'Other parts & assembly', examples: [
        { label: 'Create a component', prompt: 'Create a standard demonstration pylon and tell me its dimensions.' },
        { label: 'Adjust a component', prompt: 'Set my pylon length to 250 mm. If I have more than one pylon, ask me which one to change.' },
        { label: 'Assemble the parts', prompt: 'Assemble my socket, adapter, pylon and foot, then report the total height. Ask me to choose if parts are missing or there are multiple versions.' },
      ] },
    ],
  },
  '/printer': {
    intro: 'Ask about printer readiness, prepare your file, or check an active job. Starting a print still requires your approval.',
    groups: [
      { title: 'Prepare & print', examples: [
        { label: 'Check printer', prompt: 'Check whether the virtual printer is connected and ready.' },
        { label: 'Prepare my socket', prompt: 'Prepare my confirmed socket for printing. Ask me which slicing profile to use, and reuse an existing prepared job if it matches. Do not start printing yet.' },
        { label: 'Slice & estimate', prompt: 'Slice my confirmed socket using the finer demo_020 profile. Tell me the estimated time and filament needed without starting a print.' },
        { label: 'Start with approval', prompt: 'I want to print the prepared socket. Show me the job details and ask for my approval before starting.' },
      ] },
      { title: 'Manage a job', examples: [
        { label: 'Check progress', prompt: 'How is my current print going? Read its status and remaining time from the printer.' },
        { label: 'Cancel current print', prompt: 'Cancel my current print and report whether the printer has stopped it.' },
        { label: 'Return to socket', prompt: 'Take me back to the socket stage to review the design.' },
      ] },
    ],
  },
};
