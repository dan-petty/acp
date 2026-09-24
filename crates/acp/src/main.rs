//! CLI binary for the Agentic Communication Protocol (ACP).

use std::fs;
use std::path::PathBuf;
use std::process;

use clap::{Parser, Subcommand};

use acp::models::{EpistemicEnvelope, ACP_VERSION};

#[derive(Parser)]
#[command(name = "acp")]
#[command(about = "Agentic Communication Protocol (ACP) inspection and certification CLI")]
#[command(version = ACP_VERSION)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Validate an Epistemic State Envelope file
    Validate {
        /// Path to JSON envelope file
        file: PathBuf,
    },
    /// Inspect and display a human- and agent-readable summary of an envelope
    Inspect {
        /// Path to JSON envelope file
        file: PathBuf,
    },
    /// Print protocol version
    Version,
}

fn load_envelope(path: &PathBuf) -> Result<EpistemicEnvelope, Box<dyn std::error::Error>> {
    let content = fs::read_to_string(path)?;
    let envelope: EpistemicEnvelope = serde_json::from_str(&content)?;
    envelope.validate()?;
    Ok(envelope)
}

fn main() {
    let cli = Cli::parse();

    match cli.command {
        Commands::Version => {
            println!("ACP v{}", ACP_VERSION);
        }
        Commands::Validate { file } => match load_envelope(&file) {
            Ok(envelope) => {
                println!(
                    "✅ Envelope '{}' is structurally valid (ACP v{}).",
                    envelope.envelope_id, envelope.acp_version
                );
            }
            Err(err) => {
                eprintln!("❌ Envelope validation failed: {}", err);
                process::exit(1);
            }
        },
        Commands::Inspect { file } => match load_envelope(&file) {
            Ok(env) => {
                let leash = &env.budget_leash;
                let commit_short = if env.workspace_context.commit_base.len() >= 8 {
                    &env.workspace_context.commit_base[..8]
                } else {
                    &env.workspace_context.commit_base
                };
                println!("=== ACP Epistemic Envelope: {} ===", env.envelope_id);
                println!("Version:      {}", env.acp_version);
                println!("Traceparent:  {}", env.traceparent);
                println!("Goal:         {}", env.telos.goal);
                println!(
                    "Repository:   {} @ {}",
                    env.workspace_context.repository, commit_short
                );
                println!("Budget Leash:");
                println!("  - Max Tokens: {}", leash.token_limit);
                println!("  - Max Cost:   ${:.2}", leash.max_cost_usd);
                println!("  - Max Tools:  {}", leash.max_tool_invocations);
                println!("Exit Criteria ({}):", env.telos.exit_criteria.len());
                for criterion in &env.telos.exit_criteria {
                    println!("  * {}", criterion);
                }
            }
            Err(err) => {
                eprintln!("❌ Failed to inspect envelope: {}", err);
                process::exit(1);
            }
        },
    }
}
