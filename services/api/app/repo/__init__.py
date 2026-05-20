"""The ONLY place in the sample that imports from `genblaze_*`.

Anything outside this package must depend on Genblaze types only
transitively (via the Pydantic models the runtime returns).
"""
