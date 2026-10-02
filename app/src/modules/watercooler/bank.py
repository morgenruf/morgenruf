"""The built-in watercooler questions.

Every workspace shares this list and can hide any of it for itself. A key is
stable forever: rotation, hiding and the posts table refer to it, so a
question's wording may be fixed but its key never reused for another one.
Keys come from a question's position in its list, so only ever append: never
reorder or delete. To drop a question, add its key to RETIRED.

Chosen to be easy to answer at work, by anyone: nothing about religion,
politics, health, family status, alcohol, money or appearance.
"""

from __future__ import annotations

from dataclasses import dataclass

LIGHT = "light"
WORK = "work"
REMOTE = "remote"
THIS_OR_THAT = "this_or_that"
CATEGORIES = (LIGHT, WORK, REMOTE, THIS_OR_THAT)
CATEGORY_LABELS = {
    LIGHT: "Light",
    WORK: "Work",
    REMOTE: "Remote life",
    THIS_OR_THAT: "This or that",
}


@dataclass(frozen=True)
class Question:
    key: str
    category: str
    text: str


_LIGHT = (
    "What is a small thing that made your week better?",
    "What is the best thing you ate recently?",
    "Which song have you had on repeat lately?",
    "What is a hobby you would pick up if you had a free month?",
    "What is the most useful thing you learned from a video online?",
    "Which fictional place would you most like to visit?",
    "What is a skill you are quietly proud of?",
    "What is the last thing that made you laugh out loud?",
    "What is your go-to snack for a long afternoon?",
    "If you could instantly master one instrument, which would it be?",
    "What is a book, show or podcast you would recommend to the team?",
    "What is the best piece of advice you have been given?",
    "What did you want to be when you were ten?",
    "What is a place near you that more people should know about?",
    "What is your favourite way to spend a slow Sunday?",
    "What is a game, board or digital, you never get tired of?",
    "Which season do you like best, and why?",
    "What is something you are looking forward to this month?",
    "What is the most interesting fact you know?",
    "If you could have any animal as a sidekick, which would you choose?",
    "What is a dish you can cook really well?",
    "What is the best gift you have ever given someone?",
    "Which movie could you watch again and again?",
    "What is a word or phrase you use too often?",
    "If you had to teach a class on anything, what would it be?",
    "What is the strangest food combination you enjoy?",
    "What is your favourite sound?",
    "What is something you changed your mind about recently?",
    "What is a tradition from where you grew up that you love?",
    "If your week had a theme song, what would it be?",
    "What is the best view you have ever seen?",
    "What is a small luxury you always make room for?",
    "What would your superpower be, as long as it is a slightly useless one?",
    "What is the oldest thing you still use every day?",
    "Which emoji best describes your week so far?",
    "What is a museum or exhibit you remember well?",
    "What is something you have built or made with your hands?",
    "What is a fun fact about the town you grew up in?",
    "What is your favourite plant, or the one you keep alive against the odds?",
    "What is the best bakery or café you have ever found?",
)

_WORK = (
    "What is one tool or shortcut that saves you time every day?",
    "What does a really good day at work look like for you?",
    "What is something you learned at work this month?",
    "Who helped you out recently, and how?",
    "What is a habit that helps you focus?",
    "What is the best meeting you have ever been in, and what made it good?",
    "What is a work task you secretly enjoy?",
    "What is one thing we could stop doing as a team?",
    "What is a skill you would like to learn from someone on this team?",
    "What is the most useful feedback you have received?",
    "How do you like to plan your week?",
    "What is a project you are proud of, from any job?",
    "What is your favourite way to celebrate a win?",
    "What is a mistake that taught you something valuable?",
    "What is something about your role people might not know?",
    "Which part of your work would you happily explain to anyone who asks?",
    "What is a question you wish people asked you more often?",
    "What does your ideal focus block look like?",
    "What is a small process change that made a big difference for you?",
    "What is a resource every new teammate should know about?",
    "What is something you want to get better at this quarter?",
    "What is the best onboarding tip you could give a new starter?",
    "How do you take a proper break during the day?",
    "What would you build if you had a week with no meetings?",
    "What is a work myth you would like to bust?",
    "What is the best documentation you have ever read?",
    "What is a decision this team made that you think was a great call?",
    "What is something that always gets you unstuck?",
    "What did your first job teach you?",
    "What is your favourite way to give someone a thank you at work?",
    "What is one thing that makes a handover go smoothly?",
    "What is a goal you are working toward right now?",
    "Which colleague, past or present, taught you the most?",
    "What is something you would tell yourself on your first day here?",
    "What is a small experiment you would like the team to try?",
    "What is your favourite kind of problem to solve?",
    "When do you do your best thinking?",
    "What is a question that helps you understand a new project fast?",
)

_REMOTE = (
    "What does your workspace look like today?",
    "What is the best thing about where you work from?",
    "What is your favourite way to start the work day?",
    "How do you mark the end of your work day?",
    "What is one thing on your desk that does not need to be there but stays?",
    "What is the view from your window right now?",
    "What is your best tip for staying in touch with the team?",
    "What is a piece of gear that made working from home better?",
    "What is your favourite background noise or music for working?",
    "Where do you go when you need a change of scenery?",
    "What is your go-to lunch on a busy day?",
    "How do you keep moving during the day?",
    "What is a time zone mix-up you have lived through?",
    "What is the best coffee or tea setup you have seen?",
    "What is a small thing that makes a video call feel friendlier?",
    "What time of day do you feel most productive?",
    "What is a nice thing a teammate did for you from afar?",
    "What do you miss least about commuting, or most?",
    "What is the most unusual place you have worked from?",
    "How do you avoid notification overload?",
    "What is something that makes async work easier for you?",
    "What does a good focus day at home look like for you?",
    "What is a ritual that helps you switch off after work?",
    "What is your favourite walk near where you work?",
    "Who would you like to have a coffee chat with this week?",
    "What is your best trick for a tidy desktop, real or digital?",
    "What is a Slack habit you would recommend to everyone?",
    "What is something you have learned about working across time zones?",
    "What is the best surprise that turned up during a video call?",
    "What is your favourite way to say hello to the team in the morning?",
    "How do you take a screen break?",
    "What is a podcast or playlist that keeps you company while you work?",
    "What is one thing you would add to the perfect home office?",
    "What makes a written update easy for you to read?",
    "What is a place you would love to work from for a week?",
    "What is your favourite emoji reaction to use on Slack?",
)

_THIS_OR_THAT = (
    "Mountains or beach?",
    "Early bird or night owl?",
    "Coffee or tea?",
    "Books or podcasts?",
    "Sweet or savoury snacks?",
    "Cats or dogs?",
    "Summer or winter?",
    "Call or message?",
    "Sunrise or sunset?",
    "City break or countryside?",
    "Pancakes or waffles?",
    "Planner or improviser?",
    "Headphones or speakers?",
    "Dark mode or light mode?",
    "Paper notebook or notes app?",
    "Movies or series?",
    "Board games or video games?",
    "Spicy or mild?",
    "Rain or sunshine?",
    "Window seat or aisle?",
    "Cook at home or eat out?",
    "Text with emoji or without?",
    "Fiction or non-fiction?",
    "Big team event or small get-together?",
    "Standing desk or sitting?",
    "Live music or a good album at home?",
    "Hot chocolate or iced coffee?",
    "Inbox zero or inbox chaos?",
    "Road trip or train journey?",
    "Puzzles or crosswords?",
    "Long walk or quick run?",
    "Keyboard shortcuts or mouse?",
    "Popcorn: salty or sweet?",
    "Museum or theme park?",
    "Bright colours or neutrals?",
    "Morning meetings or afternoon meetings?",
)


# Keys of questions taken out of rotation for everyone. Their keys stay taken.
RETIRED: frozenset[str] = frozenset()


def _build() -> tuple[Question, ...]:
    out: list[Question] = []
    for category, texts, prefix in (
        (LIGHT, _LIGHT, "light"),
        (WORK, _WORK, "work"),
        (REMOTE, _REMOTE, "remote"),
        (THIS_OR_THAT, _THIS_OR_THAT, "tot"),
    ):
        for number, text in enumerate(texts, start=1):
            key = f"{prefix}-{number:03d}"
            if key not in RETIRED:
                out.append(Question(key=key, category=category, text=text))
    return tuple(out)


QUESTIONS: tuple[Question, ...] = _build()
BY_KEY: dict[str, Question] = {q.key: q for q in QUESTIONS}


def in_categories(categories: set[str] | frozenset[str]) -> list[Question]:
    return [q for q in QUESTIONS if q.category in categories]
