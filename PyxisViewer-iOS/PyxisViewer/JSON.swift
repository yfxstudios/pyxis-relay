import Foundation

/// A JSON value from the camera, with forgiving accessors (missing keys read as .null).
enum JSON: Equatable {
    case null
    case bool(Bool)
    case number(Double)
    case string(String)
    case array([JSON])
    case object([String: JSON])

    init(_ any: Any?) {
        switch any {
        case nil, is NSNull: self = .null
        case let n as NSNumber:
            // JSONSerialization gives NSNumber for both; CFBoolean tells booleans apart
            self = CFGetTypeID(n) == CFBooleanGetTypeID() ? .bool(n.boolValue) : .number(n.doubleValue)
        case let s as String: self = .string(s)
        case let a as [Any]: self = .array(a.map { JSON($0) })
        case let d as [String: Any]: self = .object(d.mapValues { JSON($0) })
        default: self = .null
        }
    }

    init(data: Data) {
        self = (try? JSONSerialization.jsonObject(with: data, options: [.fragmentsAllowed])).map { JSON($0) } ?? .null
    }

    var any: Any {
        switch self {
        case .null: return NSNull()
        case .bool(let b): return b
        case .number(let n): return n == n.rounded() && abs(n) < 1e15 ? Int(n) as Any : n
        case .string(let s): return s
        case .array(let a): return a.map(\.any)
        case .object(let o): return o.mapValues(\.any)
        }
    }

    var data: Data { (try? JSONSerialization.data(withJSONObject: any, options: [.fragmentsAllowed])) ?? Data() }

    subscript(key: String) -> JSON {
        if case .object(let o) = self { return o[key] ?? .null }
        return .null
    }
    subscript(index: Int) -> JSON {
        if case .array(let a) = self, a.indices.contains(index) { return a[index] }
        return .null
    }

    var isNull: Bool { self == .null }
    var double: Double? { if case .number(let n) = self { return n }; return nil }
    var int: Int? { double.map { Int($0.rounded()) } }
    var bool: Bool? { if case .bool(let b) = self { return b }; return nil }
    var string: String? { if case .string(let s) = self { return s }; return nil }
    var array: [JSON] { if case .array(let a) = self { return a }; return [] }
    var object: [String: JSON] { if case .object(let o) = self { return o }; return [:] }

    /// This object with `other`'s keys merged in (recursively), for optimistic updates.
    func merged(with other: JSON) -> JSON {
        guard case .object(var mine) = self, case .object(let theirs) = other else { return other }
        for (k, v) in theirs { mine[k] = (mine[k] ?? .null).merged(with: v) }
        return .object(mine)
    }
}

extension JSON: ExpressibleByDictionaryLiteral, ExpressibleByArrayLiteral, ExpressibleByStringLiteral,
                ExpressibleByIntegerLiteral, ExpressibleByFloatLiteral, ExpressibleByBooleanLiteral {
    init(dictionaryLiteral elements: (String, JSON)...) { self = .object(Dictionary(uniqueKeysWithValues: elements)) }
    init(arrayLiteral elements: JSON...) { self = .array(elements) }
    init(stringLiteral value: String) { self = .string(value) }
    init(integerLiteral value: Int) { self = .number(Double(value)) }
    init(floatLiteral value: Double) { self = .number(value) }
    init(booleanLiteral value: Bool) { self = .bool(value) }
}
