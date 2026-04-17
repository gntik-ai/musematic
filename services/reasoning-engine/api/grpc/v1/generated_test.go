package reasoningv1

import (
	"context"
	"reflect"
	"strings"
	"testing"

	"github.com/musematic/reasoning-engine/internal/correction_loop"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/reflect/protoreflect"
)

type protoCoverageMessage interface {
	Reset()
	String() string
	ProtoMessage()
	ProtoReflect() protoreflect.Message
	Descriptor() ([]byte, []int)
}

func exerciseMessage(t *testing.T, message protoCoverageMessage) {
	t.Helper()

	_ = message.String()
	_, _ = message.Descriptor()
	_ = message.ProtoReflect().Descriptor()
	message.ProtoMessage()

	value := reflect.ValueOf(message)
	typ := value.Type()
	for index := 0; index < typ.NumMethod(); index++ {
		method := typ.Method(index)
		if strings.HasPrefix(method.Name, "Get") && method.Type.NumIn() == 1 {
			value.Method(index).Call(nil)
		}
	}

	message.Reset()
}

func exerciseNilGetterPaths(t *testing.T, message protoCoverageMessage) {
	t.Helper()

	value := reflect.Zero(reflect.TypeOf(message))
	typ := value.Type()
	for index := 0; index < typ.NumMethod(); index++ {
		method := typ.Method(index)
		if strings.HasPrefix(method.Name, "Get") && method.Type.NumIn() == 1 {
			value.Method(index).Call(nil)
		}
	}
}

func TestGeneratedMessagesAndEnums(t *testing.T) {
	t.Parallel()

	messages := []protoCoverageMessage{
		&SelectReasoningModeRequest{},
		&BudgetConstraints{},
		&ReasoningModeConfig{},
		&BudgetAllocation{},
		&AllocateReasoningBudgetRequest{},
		&ReasoningBudgetEnvelope{},
		&GetBudgetStatusRequest{},
		&BudgetStatusResponse{},
		&StreamBudgetEventsRequest{},
		&BudgetEvent{},
		&ReasoningTraceEvent{},
		&ReasoningTraceAck{},
		&CreateTreeBranchRequest{},
		&TreeBranchHandle{},
		&EvaluateTreeBranchesRequest{},
		&BranchSelectionResult{},
		&BranchSummary{},
		&StartSelfCorrectionRequest{},
		&SelfCorrectionHandle{},
		&CorrectionIterationEvent{},
		&ConvergenceResult{},
	}
	for _, message := range messages {
		exerciseMessage(t, message)
		exerciseNilGetterPaths(t, message)
	}

	_ = ReasoningMode_REASONING_MODE_UNSPECIFIED.Enum()
	_ = ReasoningMode_DIRECT.String()
	_ = ReasoningMode_TREE_OF_THOUGHT.Descriptor()
	_ = ReasoningMode_REACT.Type()
	_ = ReasoningMode_DEBATE.Number()
	_, _ = ReasoningMode_CODE_AS_REASONING.EnumDescriptor()

	_ = ConvergenceStatus_CONVERGENCE_STATUS_UNSPECIFIED.Enum()
	_ = ConvergenceStatus_CONTINUE.String()
	_ = ConvergenceStatus_CONVERGED.Descriptor()
	_ = ConvergenceStatus_BUDGET_EXCEEDED.Type()
	_ = ConvergenceStatus_ESCALATE_TO_HUMAN.Number()
	_, _ = ConvergenceStatus_CONTINUE.EnumDescriptor()
}

func TestUnimplementedReasoningEngineServiceServer(t *testing.T) {
	t.Parallel()

	server := UnimplementedReasoningEngineServiceServer{}
	if _, err := server.SelectReasoningMode(context.Background(), &SelectReasoningModeRequest{}); status.Code(err) != codes.Unimplemented {
		t.Fatalf("SelectReasoningMode() error = %v", err)
	}
	if _, err := server.AllocateReasoningBudget(context.Background(), &AllocateReasoningBudgetRequest{}); status.Code(err) != codes.Unimplemented {
		t.Fatalf("AllocateReasoningBudget() error = %v", err)
	}
	if _, err := server.GetReasoningBudgetStatus(context.Background(), &GetBudgetStatusRequest{}); status.Code(err) != codes.Unimplemented {
		t.Fatalf("GetReasoningBudgetStatus() error = %v", err)
	}
	if err := server.StreamBudgetEvents(&StreamBudgetEventsRequest{}, nil); status.Code(err) != codes.Unimplemented {
		t.Fatalf("StreamBudgetEvents() error = %v", err)
	}
	if err := server.StreamReasoningTrace(nil); status.Code(err) != codes.Unimplemented {
		t.Fatalf("StreamReasoningTrace() error = %v", err)
	}
	if _, err := server.CreateTreeBranch(context.Background(), &CreateTreeBranchRequest{}); status.Code(err) != codes.Unimplemented {
		t.Fatalf("CreateTreeBranch() error = %v", err)
	}
	if _, err := server.EvaluateTreeBranches(context.Background(), &EvaluateTreeBranchesRequest{}); status.Code(err) != codes.Unimplemented {
		t.Fatalf("EvaluateTreeBranches() error = %v", err)
	}
	if _, err := server.StartSelfCorrectionLoop(context.Background(), &StartSelfCorrectionRequest{}); status.Code(err) != codes.Unimplemented {
		t.Fatalf("StartSelfCorrectionLoop() error = %v", err)
	}
	if _, err := server.SubmitCorrectionIteration(context.Background(), &CorrectionIterationEvent{}); status.Code(err) != codes.Unimplemented {
		t.Fatalf("SubmitCorrectionIteration() error = %v", err)
	}
	server.testEmbeddedByValue()
}

func TestProtoConversionHelpers(t *testing.T) {
	t.Parallel()

	if got := modeToProto("DIRECT"); got != ReasoningMode_DIRECT {
		t.Fatalf("modeToProto(DIRECT) = %v", got)
	}
	if got := modeToProto("CHAIN_OF_THOUGHT"); got != ReasoningMode_CHAIN_OF_THOUGHT {
		t.Fatalf("modeToProto(CHAIN_OF_THOUGHT) = %v", got)
	}
	if got := modeToProto("TREE_OF_THOUGHT"); got != ReasoningMode_TREE_OF_THOUGHT {
		t.Fatalf("modeToProto(TREE_OF_THOUGHT) = %v", got)
	}
	if got := modeToProto("REACT"); got != ReasoningMode_REACT {
		t.Fatalf("modeToProto(REACT) = %v", got)
	}
	if got := modeToProto("CODE_AS_REASONING"); got != ReasoningMode_CODE_AS_REASONING {
		t.Fatalf("modeToProto(CODE_AS_REASONING) = %v", got)
	}
	if got := modeToProto("DEBATE"); got != ReasoningMode_DEBATE {
		t.Fatalf("modeToProto(DEBATE) = %v", got)
	}
	if got := modeToProto("unknown"); got != ReasoningMode_REASONING_MODE_UNSPECIFIED {
		t.Fatalf("modeToProto(unknown) = %v", got)
	}

	if got := convergenceToProto(correction_loop.StatusContinue); got != ConvergenceStatus_CONTINUE {
		t.Fatalf("convergenceToProto(continue) = %v", got)
	}
	if got := convergenceToProto(correction_loop.StatusConverged); got != ConvergenceStatus_CONVERGED {
		t.Fatalf("convergenceToProto(converged) = %v", got)
	}
	if got := convergenceToProto(correction_loop.StatusBudgetExceeded); got != ConvergenceStatus_BUDGET_EXCEEDED {
		t.Fatalf("convergenceToProto(budget_exceeded) = %v", got)
	}
	if got := convergenceToProto(correction_loop.StatusEscalateToHuman); got != ConvergenceStatus_ESCALATE_TO_HUMAN {
		t.Fatalf("convergenceToProto(escalate) = %v", got)
	}
	if got := convergenceToProto("unknown"); got != ConvergenceStatus_CONVERGENCE_STATUS_UNSPECIFIED {
		t.Fatalf("convergenceToProto(unknown) = %v", got)
	}

	if got := safeInt32(1 << 40); got <= 0 {
		t.Fatalf("safeInt32(overflow) = %d", got)
	}
	if got := safeInt32(-(1 << 40)); got >= 0 {
		t.Fatalf("safeInt32(underflow) = %d", got)
	}
}
