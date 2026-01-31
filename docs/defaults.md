# Defaults Configuration

This document describes the defaults configuration feature for unattended deployment.

## Overview

The `--defaults` flag allows you to run the deployment tool without interactive prompts. This is useful for:
- Unattended/automated deployments
- Quick one-command setups
- Scripting and CI/CD integration
- Aliases for frequently used configurations

When using `--defaults`, the tool reads configuration from environment variables in your `.env` file instead of prompting for input.

## Usage

```bash
python main.py deploy --defaults
```

This command will:
1. Skip interactive prompts for template, network volume, and GPU selection
2. Use default values from `.env`
3. Automatically select the cheapest GPU matching your criteria
4. Display reduced output (no GPU selection table)

## Environment Variables

The following environment variables can be set in your `.env` file:

### DEFAULT_TEMPLATE

Specifies the name of the template to use.

```
DEFAULT_TEMPLATE=simple_glm-4.7-flash
```

- **Type**: String
- **Required**: Yes (when using `--defaults`)
- **Behavior**: The tool will look for a template with exactly this name
- **Error**: If the template is not found, deployment will fail with an error

### DEFAULT_NETWORK_VOLUME

Specifies the network volume to use, or `null` for no network storage.

```
DEFAULT_NETWORK_VOLUME=null
# or
DEFAULT_NETWORK_VOLUME=storage-ro
```

- **Type**: String or "null"
- **Required**: No (defaults to null)
- **Behavior**:
  - If set to a volume name: The tool will use the specified network volume
  - If set to "null" or not set: No network volume will be used
- **Note**: When using `null`, the pod will use container disk storage instead of a network volume. This allows for "zero costs when not running" setups, but provides no data persistence.

### DEFAULT_ALLOW_TWO_GPUS

Controls whether dual GPU configurations are considered.

```
DEFAULT_ALLOW_TWO_GPUS=false
```

- **Type**: Boolean ("true" or "false")
- **Required**: No (defaults to false)
- **Behavior**:
  - `true`: Include both single and dual GPU configurations
  - `false`: Only include single GPU configurations
- **Example**: When `false`, Qty=2 options are filtered out, even if they're cheaper

### DEFAULT_MIN_COST_PER_HOUR

Minimum hourly cost filter for GPU selection.

```
DEFAULT_MIN_COST_PER_HOUR=0.30
```

- **Type**: Float (USD per hour)
- **Required**: No (no minimum filter)
- **Behavior**: GPUs with hourly cost below this value are excluded
- **Use Case**: Filter out very low-performance GPUs by setting a minimum cost threshold

### DEFAULT_MAX_COST_PER_HOUR

Maximum hourly cost filter for GPU selection.

```
DEFAULT_MAX_COST_PER_HOUR=0.80
```

- **Type**: Float (USD per hour)
- **Required**: No (no maximum filter)
- **Behavior**: GPUs with hourly cost above this value are excluded
- **Use Case**: Avoid "overkill" setups by setting a maximum cost threshold

### DEFAULT_MODEL

Specifies the Ollama model to preseed in container-only setups.

```
DEFAULT_MODEL=glm-4.7-flash
```

- **Type**: String
- **Required**: No (only used if `DEFAULT_PRESEED=true`)
- **Behavior**: Model name passed to `ollama pull` command
- **Use Case**: Preload models in ephemeral container setups (no network volume)
- **Example**: "llama3.1", "glm-4.7-flash", "mistral-7b"

### DEFAULT_PRESEED

Controls whether to automatically preseed the model in container-only setups.

```
DEFAULT_PRESEED=true
```

- **Type**: Boolean ("true" or "false")
- **Required**: No (defaults to false)
- **Behavior**: If `true` and no network volume is used, runs `ollama pull` after tunnels are established
- **Use Case**: Automatically download models to container disk for faster startup
- **Note**: Only applies when `DEFAULT_NETWORK_VOLUME=null` (container-only setup)

## Workflow with Defaults

When you run `python main.py deploy --defaults`, the following happens:

1. **Configuration Loading**
   - Load all default values from `.env`
   - Validate that required defaults are set

2. **Template Selection**
   - Find template matching `DEFAULT_TEMPLATE` by name
   - **Fail** if template not found

3. **Network Volume Selection**
   - If `DEFAULT_NETWORK_VOLUME` is set: Find volume by name, use its datacenter
   - If `DEFAULT_NETWORK_VOLUME` is "null" or unset: No network volume, query GPUs across all regions

4. **GPU Selection**
   - Apply filters: `DEFAULT_MIN_COST_PER_HOUR`, `DEFAULT_MAX_COST_PER_HOUR`, `DEFAULT_ALLOW_TWO_GPUS`
   - Query available GPUs in the datacenter (or across all regions)
   - Filter GPUs by cost range and dual-GPU preference
   - Select cheapest matching GPU automatically
   - Display selected GPU (no table shown)

 5. **Pod Deployment**
    - Deploy pod with selected configuration
    - Wait for pod to be running
    - Create SSH tunnels
    - **Model Preseeding** (if no network volume AND `DEFAULT_PRESEED=true`):
      - Execute `ollama pull <model>` on the pod via SSH
      - Continue with warning if preseeding fails

6. **Existing Pod Check**
   - Still prompts to reuse existing running pods (if any)
   - This behavior can be skipped with `--no-reuse` flag

## Output Differences

When using `--defaults`, the output is reduced:

| Regular Mode | Defaults Mode |
|-------------|---------------|
| Available Templates table | ✗ Not shown (template auto-selected) |
| Available Network Volumes table | ✗ Not shown (volume auto-selected) |
| Available GPUs table | ✗ Not shown (GPU auto-selected) |
| Selected GPU info | ✓ Always shown |
| Connection details | ✓ Always shown |
| Progress bars | ✓ Always shown |

## Example Configuration

Example `.env` file for unattended deployment with model preseeding:

```bash
# Required: API key
RUNPOD_API_KEY=rpa_your_api_key_here

# Defaults configuration
DEFAULT_TEMPLATE=simple_glm-4.7-flash
DEFAULT_NETWORK_VOLUME=null
DEFAULT_ALLOW_TWO_GPUS=false
DEFAULT_MIN_COST_PER_HOUR=0.30
DEFAULT_MAX_COST_PER_HOUR=0.80

# Model preseeding (for container-only setups)
DEFAULT_MODEL=glm-4.7-flash
DEFAULT_PRESEED=true
```

With this configuration:
1. Uses the "simple_glm-4.7-flash" template
2. No network volume (container disk storage)
3. Only single GPU configurations
4. GPUs between $0.30-$0.80/hr
5. Cheapest matching GPU is selected automatically
6. Preseeds "glm-4.7-flash" model after deployment

## Combining with Other Flags

The `--defaults` flag can be combined with other flags:

```bash
# Skip existing pod check + use defaults
python main.py deploy --defaults --no-reuse

# Keep pod running after exit + use defaults
python main.py deploy --defaults --no-cleanup

# Skip existing pod, keep running, use defaults
python main.py deploy --defaults --no-reuse --no-cleanup
```

## Behavior Details

### Template Not Found

If `DEFAULT_TEMPLATE` doesn't match any existing template:
```
✗ Template 'my-template' not found. Available templates:
  - simple_glm-4.7-flash
  - another-template
```

The deployment will fail. You need to update `.env` with a valid template name.

### Network Volume Not Found

If `DEFAULT_NETWORK_VOLUME` is set but the volume doesn't exist:
```
✗ Network volume 'my-storage' not found. Available volumes:
  - storage-ro
  - storage-rw
```

The deployment will fail. You need to update `.env` with a valid volume name or use "null".

### No GPUs in Cost Range

If no GPUs match your cost filters:
```
✗ No available GPU configuration found matching criteria in All regions.
Try checking another datacenter or lowering requirements.
```

The deployment will fail. Adjust `DEFAULT_MIN_COST_PER_HOUR` or `DEFAULT_MAX_COST_PER_HOUR`.

### Using "null" Network Volume

When `DEFAULT_NETWORK_VOLUME=null`:
- No network volume is attached to pod
- Pod uses container disk storage (non-persistent)
- Data is lost when the pod is terminated
- Allows for "zero costs when not running" since you only pay for the pod while it's running
- GPU selection happens across all datacenters (not tied to a volume's datacenter)
- If `DEFAULT_PRESEED=true`, the model specified by `DEFAULT_MODEL` will be automatically downloaded via `ollama pull`

## Aliasing for Quick Access

You can create shell aliases for quick access:

```bash
# Add to ~/.bashrc or ~/.zshrc
alias runpod-deploy='python /path/to/runpod_simple/main.py deploy --defaults'
```

Then simply run:
```bash
runpod-deploy
```

## Error Messages

Common error messages when using defaults:

| Error | Cause | Solution |
|-------|-------|----------|
| `DEFAULT_TEMPLATE not set in .env` | Missing template name | Add `DEFAULT_TEMPLATE=...` to `.env` |
| `Template 'X' not found` | Template name doesn't match | Check available templates with `python main.py deploy` and update `.env` |
| `Network volume 'X' not found` | Volume name doesn't match | Check available volumes with `python main.py deploy` and update `.env` |
| `No available GPU configuration found` | Cost filters too restrictive | Adjust min/max cost filters in `.env` |
| `Model preseeding failed` | `ollama pull` command failed | Check model name is correct, check pod logs, continue with warning |
