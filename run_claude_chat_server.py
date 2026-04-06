#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entry point for the Claude Agent server."""

from run_model_chat_server import main


if __name__ == '__main__':
    main(
        default_config_filename='claude_agent_config.json',
        cli_description='Run Claude Agent server.',
        startup_label='Claude Agent Server',
        access_label='Claude Agent UI',
        app_factory_import='claude_agent.claude_app:create_claude_app',
    )
