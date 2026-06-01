from eslams.agent import AgentServer

server = AgentServer(agent_id="example-random-agent", version="1.0.0")


@server.act
def act(request):
    return {
        "action": request.legal_actions[0],
        "confidence": 0.5,
        "public_explanation": "Example agent selected the first legal action.",
    }


if __name__ == "__main__":
    server.run(port=8000)
