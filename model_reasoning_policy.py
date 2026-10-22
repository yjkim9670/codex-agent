"""Company gateway model policies shared by the service and diagnostic runner."""
import re


def company_reasoning_options(model):
    name = str(model or '').lower().rsplit('/', 1)[-1]
    compact = re.sub(r'[^a-z0-9]', '', name)
    # The later Qwen3.8 family instruction takes precedence over the on/off note.
    if compact.startswith('qwen38'):
        return ['low', 'medium', 'xhigh']
    if compact.startswith(('gemma', 'gauss')):
        return ['on', 'off']
    if str(model or '').lower().startswith('openai/') or compact.startswith('gptoss'):
        return ['low', 'medium', 'high']
    return None
