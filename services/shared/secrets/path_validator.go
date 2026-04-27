package secrets

import (
	"fmt"
	"regexp"
)

var canonicalPathRE = regexp.MustCompile(`^secret/data/musematic/(production|staging|dev|test|ci)/(oauth|model-providers|notifications|ibor|audit-chain|connectors|accounts)/[a-zA-Z0-9_/-]+$`)

func ValidatePath(path string) error {
	if canonicalPathRE.MatchString(path) {
		return nil
	}
	return fmt.Errorf("%w: %s", ErrInvalidVaultPath, path)
}
