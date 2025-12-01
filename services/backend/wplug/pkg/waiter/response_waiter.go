package waiter

import (
	"sync"
	"wplug/pkg/message"
)

type ResponseWaiter struct {
	mu   sync.Mutex
	wait map[string]chan message.Message
}

var respWaiters = make([]*ResponseWaiter, 1)

// GetResponseWaiter is used to enable that all async components use the same ResponseWaiter
func GetResponseWaiter() *ResponseWaiter {
	if len(respWaiters) == 0 {
		respWaiters = append(respWaiters, NewResponseWaiter())
	}

	return respWaiters[0]
}

func NewResponseWaiter() *ResponseWaiter {
	return &ResponseWaiter{
		wait: make(map[string]chan message.Message),
	}
}

func (rw *ResponseWaiter) Register(msgID string) chan message.Message {
	rw.mu.Lock()
	defer rw.mu.Unlock()

	ch := make(chan message.Message, 1)
	rw.wait[msgID] = ch
	return ch
}

func (rw *ResponseWaiter) Deliver(msg message.Message) {
	rw.mu.Lock()
	ch, exists := rw.wait[msg.DeviceInfo.DeviceID]
	if exists {
		delete(rw.wait, msg.DeviceInfo.DeviceID)
	}

	rw.mu.Unlock()

	if exists {
		ch <- msg
	}
}
