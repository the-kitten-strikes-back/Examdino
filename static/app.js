document.addEventListener("DOMContentLoaded", () => {
  const quizCards = document.querySelectorAll(".quiz-card");
  const quizScore = document.getElementById("quiz-score");
  let score = 0;

  quizCards.forEach((card) => {
    const correctIndex = Number(card.dataset.correct || 0);
    const feedback = card.querySelector(".quiz-feedback");
    const options = Array.from(card.querySelectorAll(".quiz-option"));

    options.forEach((option) => {
      option.addEventListener("click", () => {
        if (card.dataset.answered === "true") {
          return;
        }
        card.dataset.answered = "true";
        options.forEach((button) => button.classList.remove("correct", "wrong"));
        const selectedIndex = Number(option.dataset.index);
        const correctOption = options[correctIndex];

        if (selectedIndex === correctIndex) {
          option.classList.add("correct");
          if (feedback) {
            feedback.textContent = "Correct. Strong recall.";
          }
          score += 1;
        } else {
          option.classList.add("wrong");
          if (correctOption) {
            correctOption.classList.add("correct");
          }
          if (feedback) {
            feedback.textContent = "Not quite. The correct answer has been highlighted.";
          }
        }

        options.forEach((button) => {
          button.disabled = true;
        });

        if (quizScore) {
          quizScore.textContent = `Score: ${score} / ${quizCards.length}`;
        }
      });
    });
  });
});
