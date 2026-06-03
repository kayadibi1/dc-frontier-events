from aggregator.normalize import detect_topics


def test_modern_ai_terms_detected():
    assert "llm" in detect_topics("Protecting kids from chatbots")
    assert "llm" in detect_topics("Foundation models and the economy")
    assert "llm" in detect_topics("The rise of AI agents in government")
    assert "llm" in detect_topics("Agentic AI for national security")
    assert "deep-learning" in detect_topics("Multimodal models for vision")


def test_robot_detected_not_just_robotic():
    # bare "robot(s)" is robotics too (e.g. "Robot Policies", "robot learning")
    assert "robotics" in detect_topics("Learning Robot Policies from Human Guidance")
    assert "robotics" in detect_topics("Robots in manufacturing")
    assert "robotics" in detect_topics("robotic manipulation")   # existing still works


def test_precision_preserved_no_overmatch():
    # bare 'agent' / 'foundation' / 'inference' must NOT trip the AI topics
    assert detect_topics("An agent of change in the community") == []
    assert detect_topics("The Heritage Foundation gala dinner") == []
    assert detect_topics("Statistical inference methods seminar") == []
