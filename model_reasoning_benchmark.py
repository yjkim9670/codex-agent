"""Versioned, deterministic reasoning probe; no provider or filesystem access."""
import itertools
import json

VERSION = 'constraints-v1'
ITEMS = [('A', 6, 13), ('B', 4, 9), ('C', 7, 16), ('D', 3, 7),
         ('E', 5, 12), ('F', 8, 20), ('G', 2, 4), ('H', 9, 22),
         ('I', 4, 10), ('J', 6, 15)]
JOBS = [('P', 3, 4), ('Q', 2, 7), ('R', 4, 2), ('S', 1, 8), ('T', 3, 5), ('U', 2, 6)]
PRECEDENCE = [('P', 'S'), ('Q', 'T'), ('R', 'U'), ('S', 'U')]


def benchmark_prompt(token):
    return f'''You are evaluating three independent reasoning problems. All information needed is
provided below. Do not inspect the workspace, call tools, run code, browse, or change files.
Use the model's configured reasoning setting. Work out the answers internally and return
only one JSON object, without a Markdown fence or a long explanation. Do not merely echo
the request marker. Accuracy and satisfying all constraints matter more than verbosity.
The same problems are used for every model and reasoning setting, so do not change or
relax any constraint. A feasible but suboptimal answer is incorrect.

Problem 1: constrained project selection.
Each project is indivisible and can be selected at most once. Costs and benefits add.
The available projects (ID, cost, benefit) are:
{json.dumps(ITEMS)}
Choose a subset with total cost at most 23 and at most five projects. Selecting C requires
A. Selecting F requires B. Selecting H requires D. Selecting J requires E. A and H cannot
both be selected. F and I cannot both be selected. At least one of C, F, H must be selected.
Maximize total benefit. If multiple subsets achieve the maximum, choose the one with the
smallest total cost; if still tied, sort each subset's IDs alphabetically and choose the
lexicographically smallest list. Return the sorted IDs as selection and total benefit as
value. Check both the dependencies and exclusions; the highest benefit/cost ratio alone
is not sufficient to solve this problem.

Problem 2: scheduling with precedence and weighted completion times.
One machine processes six jobs, each exactly once, one at a time. It starts at time zero,
there is no preemption, no idle time, and all jobs are initially available except for their
precedence constraints. Jobs (ID, duration, weight) are:
{json.dumps(JOBS)}
Precedence pairs (earlier job, later job) are {json.dumps(PRECEDENCE)}.
A job's completion time is the sum of durations of all jobs up to and including that job.
Minimize the sum over all jobs of weight multiplied by completion time. If multiple orders
have the same minimum, choose the lexicographically smallest sequence of job IDs.
Return all six IDs in execution order as order and the minimum objective as cost.
Do not confuse start times with completion times or optimize unweighted completion time.

Problem 3: sequential checksum.
Start with x=17. For each integer i from 1 through 40 inclusive, first compute
x=(7*x+i*i) modulo 101. Then, using that newly computed x, if i is divisible by 3,
replace x by (x+19) modulo 101. After that, if i is divisible by 5, replace x by
(3*x+1) modulo 101. When both conditions apply, the addition happens before the
multiplication. Return only the final x as checksum. Do not reset x between iterations.

Your JSON must contain exactly these fields: token (the string {token}), selection
(an array of project ID strings), value (an integer), order (an array of job ID strings),
cost (an integer), checksum (an integer). Include the marker exactly as token so the
runner can verify response persistence. Return the answers, not an algorithm or code.'''


def expected_answers():
    subsets = []
    for mask in range(1 << len(ITEMS)):
        selected = [item for i, item in enumerate(ITEMS) if mask & (1 << i)]
        ids = [item[0] for item in selected]
        cost = sum(item[1] for item in selected)
        if cost > 23 or len(ids) > 5 or not set(ids) & {'C', 'F', 'H'}:
            continue
        if any(a in ids and b not in ids for a, b in [('C', 'A'), ('F', 'B'), ('H', 'D'), ('J', 'E')]):
            continue
        if {'A', 'H'} <= set(ids) or {'F', 'I'} <= set(ids):
            continue
        subsets.append((-sum(item[2] for item in selected), cost, ids))
    value, _, selection = min(subsets)
    schedules = []
    for jobs in itertools.permutations(JOBS):
        order = [job[0] for job in jobs]
        if any(order.index(a) > order.index(b) for a, b in PRECEDENCE):
            continue
        elapsed = objective = 0
        for _, duration, weight in jobs:
            elapsed += duration
            objective += elapsed * weight
        schedules.append((objective, order))
    cost, order = min(schedules)
    x = 17
    for i in range(1, 41):
        x = (7*x + i*i) % 101
        if i % 3 == 0:
            x = (x + 19) % 101
        if i % 5 == 0:
            x = (3*x + 1) % 101
    return dict(selection=selection, value=-value, order=order, cost=cost, checksum=x)


def grade_response(content, token):
    expected = expected_answers()
    answer = None
    decoder = json.JSONDecoder()
    for i, char in enumerate(content or ''):
        if char != '{':
            continue
        try:
            candidate, _ = decoder.raw_decode(content[i:])
        except ValueError:
            continue
        if isinstance(candidate, dict) and candidate.get('token') == token:
            answer = candidate
    checks = {key: answer is not None and type(answer.get(key)) is type(value)
              and answer[key] == value for key, value in expected.items()}
    return dict(version=VERSION, score=sum(checks.values()), max_score=len(checks),
                correct=all(checks.values()), checks=checks, expected=expected,
                answer=answer, response_chars=len(content or ''))
