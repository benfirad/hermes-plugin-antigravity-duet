import SwiftUI
import AppKit
import Foundation

// MARK: - Sanitized Open-Source macOS Companion App for Hermes Antigravity Duet ("DAAK Duffy")
// Zero personal data, zero hardcoded private IPs. Defaults to http://127.0.0.1:8899 (or DUFFY_API_URL env var).

private struct DuffyTask: Decodable, Identifiable {
    let id: Int
    let title: String
    let category: String
    let status: String
    let modelUsed: String?
    let resultSummary: String?
    let approvalAction: String?
    let approvalCmd: String?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, title, category, status
        case modelUsed = "model_used"
        case resultSummary = "result_summary"
        case approvalAction = "approval_action"
        case approvalCmd = "approval_cmd"
        case createdAt = "created_at"
    }
}

private struct DuffyChatMsg: Decodable, Identifiable {
    let id: Int
    let agentId: String
    let sender: String
    let message: String
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, sender, message
        case agentId = "agent_id"
        case createdAt = "created_at"
    }
}

private struct DuffyAPIResponse: Decodable {
    let status: String
    let tasks: [DuffyTask]
    let chats: [DuffyChatMsg]?
}

private struct AgentCharacter: Identifiable {
    let id: String
    let name: String
    let roleTag: String
    let color: Color
    let shapeType: Int
    let defaultGreeting: String
    let defaultTime: String
}

private struct CommandItem: Identifiable {
    let id = UUID()
    let title: String
    let command: String
    let desc: String
}

private struct CuteBlobAvatar: View {
    let color: Color
    let shapeType: Int
    let size: CGFloat
    var showStarBadge: Bool = false

    var body: some View {
        ZStack(alignment: .bottomTrailing) {
            ZStack {
                Circle()
                    .fill(color.opacity(0.28))
                    .frame(width: size * 1.15, height: size * 1.15)
                    .blur(radius: size * 0.16)

                blobShape
                    .fill(
                        LinearGradient(
                            colors: [color, color.opacity(0.82)],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: size, height: size * 0.92)
                    .rotationEffect(.degrees(shapeType == 1 ? -8 : (shapeType == 2 ? 6 : -4)))

                HStack(spacing: size * 0.14) {
                    Capsule()
                        .fill(Color.black.opacity(0.78))
                        .frame(width: size * 0.09, height: size * 0.24)
                        .rotationEffect(.degrees(-8))
                    Capsule()
                        .fill(Color.black.opacity(0.78))
                        .frame(width: size * 0.09, height: size * 0.24)
                        .rotationEffect(.degrees(-8))
                }
                .offset(x: size * 0.06, y: -size * 0.02)
            }

            if showStarBadge {
                ZStack {
                    Circle()
                        .fill(Color(red: 0.98, green: 0.72, blue: 0.12))
                        .frame(width: size * 0.32, height: size * 0.32)
                    Image(systemName: "star.fill")
                        .font(.system(size: size * 0.16, weight: .bold))
                        .foregroundStyle(.white)
                }
                .offset(x: 2, y: 2)
            }
        }
    }

    private var blobShape: RoundedRectangle {
        switch shapeType {
        case 1:
            return RoundedRectangle(cornerRadius: size * 0.34, style: .continuous)
        case 2:
            return RoundedRectangle(cornerRadius: size * 0.26, style: .continuous)
        default:
            return RoundedRectangle(cornerRadius: size * 0.48, style: .continuous)
        }
    }
}

@MainActor
private final class DuffyMonitor: ObservableObject {
    @Published var online = false
    @Published var tasks: [DuffyTask] = []
    @Published var chats: [DuffyChatMsg] = []
    @Published var activeAgent: AgentCharacter? = nil
    @Published var showQuickNewTaskSheet = false
    @Published var chatInput = ""
    @Published var isWaitingAgentReply = false
    @Published var newTaskTitle = ""
    @Published var newTaskCat = "general"
    @Published var toast: String?
    @Published var detailTab = 0

    var openDetailedWindowCallback: (() -> Void)?

    private var timer: Timer?
    private let baseURL: String = ProcessInfo.processInfo.environment["DUFFY_API_URL"] ?? "http://127.0.0.1:8899"

    let chiefDuffy = AgentCharacter(
        id: "duffy",
        name: "Chief Duffy",
        roleTag: "24/7 Autonomous Lead",
        color: Color(red: 0.98, green: 0.45, blue: 0.08),
        shapeType: 0,
        defaultGreeting: "Ready 24/7. Chat with me directly or lock in an autonomous background task.",
        defaultTime: "Live"
    )

    let agents: [AgentCharacter] = [
        AgentCharacter(
            id: "research",
            name: "Scout Hiko",
            roleTag: "Deep Research Agent",
            color: Color(red: 0.96, green: 0.18, blue: 0.28),
            shapeType: 1,
            defaultGreeting: "Ready to scan repositories, papers, and web sources in the background...",
            defaultTime: "07:54"
        ),
        AgentCharacter(
            id: "swarm",
            name: "Swarm Commander",
            roleTag: "Ruflo Multi-Agent",
            color: Color(red: 0.95, green: 0.20, blue: 0.62),
            shapeType: 1,
            defaultGreeting: "Ruflo v3 multi-agent swarm ready. I can spawn coder, tester, and analyst agents...",
            defaultTime: "07:52"
        ),
        AgentCharacter(
            id: "code",
            name: "Builder Dev",
            roleTag: "Code & Refactoring",
            color: Color(red: 0.12, green: 0.48, blue: 0.98),
            shapeType: 0,
            defaultGreeting: "Point me at any module or test suite and I will prepare the patch...",
            defaultTime: "07:49"
        ),
        AgentCharacter(
            id: "ops",
            name: "Infra Guardian",
            roleTag: "System & Security",
            color: Color(red: 0.12, green: 0.80, blue: 0.38),
            shapeType: 2,
            defaultGreeting: "Monitoring local services, health checks, and approval gates...",
            defaultTime: "07:46"
        )
    ]

    let commands: [CommandItem] = [
        CommandItem(
            title: "Enqueue Autonomous Task",
            command: "/duffy add Audit repository dependencies and draft upgrade plan",
            desc: "Adds a background task to the Duet/Duffy worker queue."
        ),
        CommandItem(
            title: "Launch Ruflo Multi-Agent Swarm",
            command: "/duffy swarm",
            desc: "Checks or spawns parallel Ruflo specialist agents (coder, researcher, tester)."
        ),
        CommandItem(
            title: "List Queued Tasks",
            command: "/duffy list",
            desc: "Lists pending, running, awaiting_approval, and completed tasks."
        ),
        CommandItem(
            title: "Approve or Reject Human-in-the-Loop Action",
            command: "/duffy approve 1   |   /duffy reject 1",
            desc: "Approves or cancels a task paused at a sensitive external action gate."
        )
    ]

    init() {
        Task { await refresh() }
        timer = Timer.scheduledTimer(withTimeInterval: 4, repeats: true) { [weak self] _ in
            Task { @MainActor in await self?.refresh() }
        }
    }

    deinit {
        timer?.invalidate()
    }

    func lastPreview(for agent: AgentCharacter) -> (text: String, time: String) {
        if let lastChat = chats.last(where: { $0.agentId == agent.id }) {
            let t = String((lastChat.createdAt ?? "").suffix(8).prefix(5))
            return (lastChat.message.replacingOccurrences(of: "\n", with: " "), t.isEmpty ? agent.defaultTime : t)
        }
        return (agent.defaultGreeting, agent.defaultTime)
    }

    func messages(for agent: AgentCharacter) -> [DuffyChatMsg] {
        chats.filter { $0.agentId == agent.id }
    }

    func refresh() async {
        guard let url = URL(string: "\(baseURL)/api/status") else { return }
        var req = URLRequest(url: url)
        req.timeoutInterval = 4
        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            if let http = resp as? HTTPURLResponse, http.statusCode == 200 {
                let decoded = try JSONDecoder().decode(DuffyAPIResponse.self, from: data)
                let oldCount = self.chats.count
                self.tasks = decoded.tasks
                self.chats = decoded.chats ?? []
                if self.chats.count > oldCount, let last = self.chats.last, last.sender == "agent" {
                    self.isWaitingAgentReply = false
                }
                self.online = true
                return
            }
        } catch {}
        self.online = false
    }

    func sendChatMessage() async {
        guard let agent = activeAgent else { return }
        let msg = chatInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !msg.isEmpty, let url = URL(string: "\(baseURL)/chat") else { return }

        chatInput = ""
        isWaitingAgentReply = true

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/x-www-form-urlencoded; charset=utf-8", forHTTPHeaderField: "Content-Type")
        var comps = URLComponents()
        comps.queryItems = [
            URLQueryItem(name: "agent_id", value: agent.id),
            URLQueryItem(name: "message", value: msg)
        ]
        req.httpBody = comps.percentEncodedQuery?.data(using: .utf8)
        do {
            _ = try await URLSession.shared.data(for: req)
            await refresh()
        } catch {
            isWaitingAgentReply = false
        }
    }

    func addTask(title: String, category: String) async {
        let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, let url = URL(string: "\(baseURL)/add") else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/x-www-form-urlencoded; charset=utf-8", forHTTPHeaderField: "Content-Type")
        var comps = URLComponents()
        comps.queryItems = [
            URLQueryItem(name: "title", value: trimmed),
            URLQueryItem(name: "category", value: category)
        ]
        req.httpBody = comps.percentEncodedQuery?.data(using: .utf8)
        do {
            _ = try await URLSession.shared.data(for: req)
            await refresh()
        } catch {}
    }

    func copy(_ text: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }
}
