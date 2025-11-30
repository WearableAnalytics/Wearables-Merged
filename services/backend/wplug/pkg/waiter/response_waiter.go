package waiter

import "sync"

type ResponseWaiter struct {
	mu   sync.Mutex
	wait map[string]chan Message
}

func NewResponseWaiter() *ResponseWaiter {
	return &ResponseWaiter{
		wait: make(map[string]chan Message),
	}
}

func (rw *ResponseWaiter) Register(msgID string) chan Message {
	rw.mu.Lock()
	defer rw.mu.Unlock()

	ch := make(chan Message, 1)
	rw.wait[msgID] = ch
	return ch
}

func (rw *ResponseWaiter) Deliver(msg Message) {
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
