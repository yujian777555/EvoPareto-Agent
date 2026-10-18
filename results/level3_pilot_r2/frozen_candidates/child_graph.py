class Workflow:
    def __init__(self, llm):
        self.llm = llm
        self.solve = "Solve step by step, end with 'Answer: <num>'."
        self.check = "Recompute and confirm or correct; end with 'Answer: <num>'."

    async def __call__(self, problem):
        drafts = await __import__("asyncio").gather(*[self.llm(f"{self.solve}\n{problem}") for _ in range(3)])
        votes = [d.strip().split("Answer:")[-1].strip() for d in drafts]
        best = max(set(votes), key=votes.count)
        if votes.count(best) >= 2:
            return best
        final = await self.llm(f"{self.check}\nProblem: {problem}\nCandidate: {drafts[0]}")
        return final.strip().split("Answer:")[-1].strip()