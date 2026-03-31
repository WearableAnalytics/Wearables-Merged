package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"time"
)

type Producer struct {
	Client   *Client
	Provider *Provider
	Phases   []Phase
}

type Client struct {
	Addr       string
	AuthToken  string
	HttpClient *http.Client
}

const (
	Constant = iota
	RampUp
	RampDown
)

type Phase struct {
	Type      int // Constant / RampUp / RampDown
	StartTime time.Time
	Duration  time.Duration
	StartRPS  int
	Step      int
}

func (c *Client) CallEndpoint(ctx context.Context, payload Payload) error {
	select {
	case <-ctx.Done():
		return ctx.Err()
	default:
	}

	data, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	req, err := http.NewRequest("POST", c.Addr, bytes.NewBuffer(data))
	if err != nil {
		return err
	}

	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.AuthToken))
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.HttpClient.Do(req)
	if err != nil {
		return err
	}

	if resp.StatusCode != 200 {
		return fmt.Errorf("response was not 200: %s", resp.Status)
	}

	return nil
}

func (p *Producer) Run(ctx context.Context) {
	select {
	case <-ctx.Done():
		return
	default:
	}

	for _, phase := range p.Phases {
		if err := phase.Run(ctx, p.Client, p.Provider); err != nil {
			log.Printf("Running phase failed with err: %v", err)
		}
	}
}

func (p *Phase) Run(ctx context.Context, c *Client, provider *Provider) error {
	p.StartTime = time.Now()

	timer, ticker := time.NewTimer(p.Duration), time.NewTicker(1*time.Second)

	for {
		select {
		case <-ctx.Done():
			return nil
		case <-timer.C:
			return nil
		case <-ticker.C:
			n := p.CalculateRPS()

			if n == 0 {
				continue
			}

			subTicker := time.NewTicker(time.Duration(1000/n) * time.Millisecond)

			for i := 0; i < n; i++ {
				<-subTicker.C
				payload := provider.CreateBenchmarkMessage()
				go func() {
					err := c.CallEndpoint(ctx, payload)
					log.Println(err)
				}()
			}

		}
	}
}

func (p *Phase) CalculateRPS() int {
	var rps int

	switch p.Type {
	case Constant:
		rps = p.StartRPS
	case RampUp:
		rps = p.StartRPS + int(time.Since(p.StartTime).Seconds())*p.Step
	case RampDown:
		rps = p.StartRPS - int(time.Since(p.StartTime).Seconds())*p.Step
	}

	if rps > 1000 {
		rps = 1000
	}
	if rps < 0 {
		rps = 0
	}

	return rps
}
