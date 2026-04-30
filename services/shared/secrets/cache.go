package secrets

import (
	"sync"
	"time"
)

type cacheKey struct {
	path string
	key  string
}

type cacheEntry struct {
	value        string
	expiresAt    time.Time
	lastSuccess  time.Time
	lastAccessed time.Time
}

type secretCache struct {
	ttl          time.Duration
	maxStaleness time.Duration
	now          func() time.Time
	entries      sync.Map
}

func newSecretCache(ttl time.Duration, maxStaleness time.Duration) *secretCache {
	if ttl <= 0 {
		ttl = time.Minute
	}
	if maxStaleness <= 0 {
		maxStaleness = 5 * time.Minute
	}
	return &secretCache{
		ttl:          ttl,
		maxStaleness: maxStaleness,
		now:          time.Now,
	}
}

func (c *secretCache) getFresh(path string, key string) (string, bool) {
	raw, ok := c.entries.Load(cacheKey{path: path, key: key})
	if !ok {
		return "", false
	}
	entry, ok := raw.(cacheEntry)
	if !ok || c.now().After(entry.expiresAt) {
		return "", false
	}
	entry.lastAccessed = c.now()
	c.entries.Store(cacheKey{path: path, key: key}, entry)
	return entry.value, true
}

func (c *secretCache) getStale(path string, key string) (string, time.Duration, bool) {
	raw, ok := c.entries.Load(cacheKey{path: path, key: key})
	if !ok {
		return "", 0, false
	}
	entry, ok := raw.(cacheEntry)
	if !ok {
		return "", 0, false
	}
	age := c.now().Sub(entry.lastSuccess)
	if age < 0 || age > c.maxStaleness {
		return "", age, false
	}
	return entry.value, age, true
}

func (c *secretCache) set(path string, key string, value string) {
	now := c.now()
	c.entries.Store(cacheKey{path: path, key: key}, cacheEntry{
		value:        value,
		expiresAt:    now.Add(c.ttl),
		lastSuccess:  now,
		lastAccessed: now,
	})
}

func (c *secretCache) flush(path string) int {
	flushed := 0
	c.entries.Range(func(rawKey, _ any) bool {
		key, ok := rawKey.(cacheKey)
		if !ok {
			return true
		}
		if path == "" || key.path == path {
			c.entries.Delete(rawKey)
			flushed++
		}
		return true
	})
	return flushed
}
