package mode_selector

import (
	"strings"
	"unicode"
)

var multiStepKeywords = []string{
	"first", "then", "finally", "step 1", "step one", "step 2", "step two",
}

var codeKeywords = []string{
	"script", "function", "python", "def", "golang", "code", "program",
}

var codeAsReasoningKeywords = []string{
	"code", "script", "write a function", "write code", "python", "def",
}

var debateKeywords = []string{
	"debate", "argue both sides", "pros and cons",
}

func Score(brief string) int {
	normalized := normalize(brief)
	words := len(strings.Fields(normalized))
	score := words / 25

	multiStepHits := 0
	for _, keyword := range multiStepKeywords {
		if strings.Contains(normalized, keyword) {
			multiStepHits++
		}
	}
	score += multiStepHits
	if multiStepHits >= 2 {
		score += 2
	}

	questions := strings.Count(normalized, "?")
	if questions > 1 {
		score += questions - 1
	}

	for _, keyword := range codeKeywords {
		if strings.Contains(normalized, keyword) {
			score += 2
			break
		}
	}

	return score
}

func DetectSpecialMode(brief string) string {
	normalized := normalize(brief)

	for _, keyword := range debateKeywords {
		if strings.Contains(normalized, keyword) {
			return "DEBATE"
		}
	}

	for _, keyword := range codeAsReasoningKeywords {
		if strings.Contains(normalized, keyword) {
			return "CODE_AS_REASONING"
		}
	}

	return ""
}

func normalize(value string) string {
	return strings.Map(func(r rune) rune {
		if unicode.IsUpper(r) {
			return unicode.ToLower(r)
		}
		return r
	}, strings.TrimSpace(value))
}
