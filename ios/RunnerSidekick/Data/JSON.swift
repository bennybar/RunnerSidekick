import Foundation

/// Any JSON value: chart objects and settings are read and written field by field, without a fixed shape.
enum JSONValue: Codable, Equatable, Hashable {
    case null, bool(Bool), number(Double), string(String), array([JSONValue]), object([String: JSONValue])

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let b = try? c.decode(Bool.self) { self = .bool(b) }
        else if let n = try? c.decode(Double.self) { self = .number(n) }
        else if let s = try? c.decode(String.self) { self = .string(s) }
        else if let a = try? c.decode([JSONValue].self) { self = .array(a) }
        else { self = .object(try c.decode([String: JSONValue].self)) }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .null: try c.encodeNil()
        case .bool(let b): try c.encode(b)
        case .number(let n): try c.encode(n)
        case .string(let s): try c.encode(s)
        case .array(let a): try c.encode(a)
        case .object(let o): try c.encode(o)
        }
    }

    subscript(key: String) -> JSONValue? { if case .object(let o) = self { return o[key] } else { return nil } }
    var string: String? {
        switch self {
        case .string(let s): return s
        case .number(let n): return n == n.rounded() && abs(n) < 1e15 ? String(Int(n)) : String(n)
        case .bool(let b): return String(b)
        default: return nil
        }
    }
    var double: Double? {
        switch self {
        case .number(let n): return n
        case .string(let s): return Double(s)
        default: return nil
        }
    }
    var bool: Bool? { if case .bool(let b) = self { return b } else { return nil } }
    var array: [JSONValue] { if case .array(let a) = self { return a } else { return [] } }
    var object: [String: JSONValue]? { if case .object(let o) = self { return o } else { return nil } }
    var isNull: Bool { self == .null }

    init(_ any: Any?) {
        switch any {
        case nil, is NSNull: self = .null
        case let b as Bool: self = .bool(b)
        case let i as Int: self = .number(Double(i))
        case let d as Double: self = .number(d)
        case let s as String: self = .string(s)
        case let a as [Any?]: self = .array(a.map { JSONValue($0) })
        case let o as [String: Any?]: self = .object(o.mapValues { JSONValue($0) })
        case let v as JSONValue: self = v
        default: self = .null
        }
    }
}

/// A value with a sensible "nothing" when the server leaves it out (an empty list, false, zero).
protocol EmptyDefault { static var emptyDefault: Self { get } }
extension Array: EmptyDefault { static var emptyDefault: Self { [] } }
extension Dictionary: EmptyDefault { static var emptyDefault: Self { [:] } }
extension Bool: EmptyDefault { static var emptyDefault: Bool { false } }
extension Int: EmptyDefault { static var emptyDefault: Int { 0 } }
extension Double: EmptyDefault { static var emptyDefault: Double { 0 } }
extension String: EmptyDefault { static var emptyDefault: String { "" } }

/// Decodes a missing, null or unexpected value as its empty default instead of failing the whole report.
@propertyWrapper
struct D<V: Codable & EmptyDefault>: Codable {
    var wrappedValue: V
    init(wrappedValue: V) { self.wrappedValue = wrappedValue }
    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        wrappedValue = (try? c.decode(V.self)) ?? .emptyDefault
    }
    func encode(to encoder: Encoder) throws { var c = encoder.singleValueContainer(); try c.encode(wrappedValue) }
}

/// A Bool the server treats as true when it doesn't say.
@propertyWrapper
struct DefaultTrue: Codable {
    var wrappedValue: Bool
    init(wrappedValue: Bool) { self.wrappedValue = wrappedValue }
    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        wrappedValue = (try? c.decode(Bool.self)) ?? true
    }
    func encode(to encoder: Encoder) throws { var c = encoder.singleValueContainer(); try c.encode(wrappedValue) }
}

extension KeyedDecodingContainer {
    func decode<V>(_ t: D<V>.Type, forKey k: Key) throws -> D<V> {
        (try? decodeIfPresent(t, forKey: k)) ?? D(wrappedValue: .emptyDefault)
    }
    func decode(_ t: DefaultTrue.Type, forKey k: Key) throws -> DefaultTrue {
        (try? decodeIfPresent(t, forKey: k)) ?? DefaultTrue(wrappedValue: true)
    }
}

enum JSON {
    /// The server's snake_case keys as Swift's camelCase. Note: dictionary keys are converted too (see `camel`).
    static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }()

    /// A snake_case key as the decoder sees it, for looking up converted dictionary keys ("resting_hr" -> "restingHr").
    static func camel(_ s: String) -> String {
        let parts = s.split(separator: "_", omittingEmptySubsequences: false)
        guard parts.count > 1 else { return s }
        return parts.enumerated().map { i, p in i == 0 ? String(p) : p.prefix(1).uppercased() + p.dropFirst() }.joined()
    }

    static func decode<T: Decodable>(_ t: T.Type, _ data: Data) throws -> T { try decoder.decode(t, from: data) }

    /// A request body from a plain dictionary (nil values become JSON null, so a cleared field clears on the server).
    static func body(_ dict: [String: Any?]) -> Data {
        (try? JSONEncoder().encode(JSONValue(dict))) ?? Data("{}".utf8)
    }
}

extension D: Equatable where V: Equatable {}
extension D: Hashable where V: Hashable {}
extension DefaultTrue: Hashable {}
