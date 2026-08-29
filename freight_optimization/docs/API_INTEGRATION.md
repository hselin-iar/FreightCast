# API Integration Notes

## Goal

Wrap the existing Python optimizer with an API.

The website should communicate with the API rather than directly
running shell commands.

## Recommended flow

POST /optimize

        |
        v

Validate request

        |
        v

Run existing pipeline / orchestration

        |
        v

Read final production result

        |
        v

Convert CSV/dataframe result to JSON

        |
        v

Return response

---

## Inputs

Possible inputs:

- maximum SAIL contracts
- risk ratio
- bunker price or live bunker mode
- planning dates
- optional scenario/objective settings

---

## Outputs

The API should expose:

### Summary

- SAIL contracts
- KILL contracts
- vessels
- routes
- departure dates
- expected value
- base value
- worst-case value

### SAIL plan

For every SAIL decision:

- contract
- vessel
- IMO
- route
- origin
- destination
- cargo
- cargo volume
- departure
- ETA
- worst incremental value
- base incremental value
- expected incremental value

### Validation

- contract violations
- capacity violations
- class violations
- temporal overlap violations

### Review opportunities

Cross-class assignments that require operational review
should remain distinguishable from automatic production decisions.

---

## Solver source

The response should identify whether the result came from:

    MILP

or:

    deterministic fallback

Do not hide fallback usage.

---

## Production architecture

Recommended eventual project structure:

    api/
        main.py
        schemas.py
        service.py

    engine/
        existing optimizer code

    data/
        raw/
        processed/

    models/

    outputs/

    run_pipeline.py

The current package is the engine/data handoff.
The API wrapper can be added by the integration developer.
