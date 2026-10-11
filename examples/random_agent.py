import random

from eslams.agent import AgentServer

server = AgentServer(agent_id="example-random-agent", version="1.0.0")


@server.act
def act(request):
    return {
        "action": random.choice(request.legal_actions),
        "confidence": 0.5,
        "public_explanation": "Example agent sampled a legal action uniformly.",
    }


if __name__ == "__main__":
    server.run(port=8000)
