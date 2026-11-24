# Job matching and CV profiles

- Entry: `profile.py` validates, loads, and analyzes the user's matching profile.
- Job suitability, location/work-mode constraints, skills, and salary matching live in `scoring.py`.
- Adjacent-role suggestions are data in `adjacent_roles.json`.
- When a CV upload fails, inspect `profile.py`; when a match score is wrong, inspect `scoring.py`.
- Profile HTTP handlers live in `../routes/`.
