# GitTama — Terminal Tamagotchi for GitHub

**Gamified terminal assistant** that turns your GitHub and DevOps workflow into a daily ritual.

Your pet reacts to commits, PRs, issues, and CI events — motivating you to keep the repository alive and clean.

## Features

- Daily quests
- 6 achievements
- Time-based state decay (pet lives even when the app is closed)
- Beautiful Rich TUI with ASCII emotions
- Persistent state (JSON)
- Mock GitHub events + easy to extend to real GitHub API
- Docker support

## Quick Start

```bash
# 1. Install
pip install -e .

# 2. Run
gittama status
