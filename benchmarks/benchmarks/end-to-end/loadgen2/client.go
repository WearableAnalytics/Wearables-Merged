package main

import (
	"context"
	"net/http"
	"time"
)

type Client struct {
	HttpClient   *http.Client
	Phases       []Phase
	DataProvider *DataProvider

	ClientConfig
}

type ClientConfig struct {
	EndpointAddr string
	AuthToken    string
}

const (
	Constant = iota
	RampUp
	RampDown
)

type Phase struct {
	Type      int
	StartTime time.Time // this will be set automatically
	Duration  time.Duration
	StartRPS  int
	Step      int
}

func (c *Client) Run(ctx context.Context) {
	select {
	case <-ctx.Done():
		return
	default:
		for _, phase := range c.Phases {
			phase.RunPhase(ctx)
		}
	}
}

func (p *Phase) RunPhase(ctx context.Context, client *Client) {
	p.StartTime = time.Now()

	timer, ticker := time.NewTimer(p.Duration), time.NewTicker(1*time.Second)

	for {
		select {
		case <-ctx.Done():
			return
		case <-timer.C:
			return
		case <-ticker.C:
			rps = p.GetCurrentRps()
			subTicker := time.NewTicker(time.Duration(1000/rps) * time.Millisecond)
			for i := 0; i < rps; i++ {
				<-subTicker.C

			}

		}

	}
}

func (p *Phase) GetCurrentRps() int {
	var rps int
	switch p.Type {
	case Constant:
		rps = p.StartRPS
	case RampUp:
		rps = p.StartRPS + int(time.Since(p.StartTime).Seconds())*p.Step
	case RampDown:
		rps = p.StartRPS - int(time.Since(p.StartTime).Seconds())*p.Step
	}

	if rps < 0 {
		rps = 0
	}
	if rps > 1000 {
		rps = 1000
	}

	return rps
}

func (c *Client) SendRequest() {
	data := c.DataProvider
}
