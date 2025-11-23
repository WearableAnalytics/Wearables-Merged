package wplug

import (
	"log"
	"math/rand"
	"time"

	"github.com/google/uuid"
)

type GenType interface {
	float64 | string
}

type Generator[T GenType] interface {
	Generate() T
}

type SimpleNumericGenerator struct {
	Base float64
	Amp  float64
}

type TimestampGenerator struct {
	Format string
}

type UuidGenerator struct{}

func (u UuidGenerator) Generate() string {
	return uuid.New().String()
}

func NewUuidGenerator() UuidGenerator {
	return UuidGenerator{}
}

type SimpleGeneratorContext struct{}

func NewSimpleNumericGenerator(base float64, amp float64) SimpleNumericGenerator {
	return SimpleNumericGenerator{
		Base: base,
		Amp:  amp,
	}
}

func (n SimpleNumericGenerator) Generate() float64 {
	log.Printf("Hello Numeric Generate gets called ")
	randVal := rand.Float64() * n.Amp

	if i := rand.Intn(2); i == 0 {
		randVal = randVal * (-1)
	}

	return n.Base + randVal
}

func NewTimestampGenerator(format string) TimestampGenerator {
	return TimestampGenerator{
		Format: format,
	}
}

func (t TimestampGenerator) Generate() string {
	log.Printf("Hello Timestamp Generate gets called ")
	return time.Now().Format(t.Format)
}
