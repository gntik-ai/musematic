package persistence

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

func NewPostgresPool(dsn string) *pgxpool.Pool {
	if dsn == "" {
		return nil
	}

	cfg, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		panic(err)
	}
	cfg.MaxConns = 20
	cfg.MinConns = 2

	pool, err := pgxpool.NewWithConfig(context.Background(), cfg)
	if err != nil {
		panic(err)
	}
	return pool
}
