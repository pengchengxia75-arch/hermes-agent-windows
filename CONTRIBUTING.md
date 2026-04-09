# Contributing to Hermes Agent Windows

Thanks for your interest in this repository.

This project is a Windows-focused adaptation of the original
[`NousResearch/hermes-agent`](https://github.com/NousResearch/hermes-agent).
The goal of this fork is simple:

- make Hermes install and run on native Windows
- avoid requiring WSL2 for normal CLI usage
- keep the install experience as close to one command as possible

## What To Contribute

The most helpful contributions are:

- Windows installation fixes
- Windows runtime compatibility fixes
- PowerShell and Git Bash integration improvements
- documentation for Windows users
- bug fixes that improve the Windows experience

## Before Opening a PR

Please test the Windows flow when your change affects install or runtime:

- `scripts/install.ps1`
- `hermes version`
- `hermes setup`
- basic local command execution through Hermes

## Scope Of This Fork

This repository is not trying to replace the upstream project.
It is a practical Windows adaptation built on top of the upstream Hermes Agent
codebase.

If your change is generally useful for all platforms, consider contributing it
upstream as well.

## Attribution

Original project:
[`NousResearch/hermes-agent`](https://github.com/NousResearch/hermes-agent)

This fork keeps the upstream MIT license and adds Windows-native install and
runtime support work on top of it.
